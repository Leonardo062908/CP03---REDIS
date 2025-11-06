"""
redis-event-app (Partes 1, 2 e 3)
---------------------------------
Parte 1: Cache de dados de evento com Redis (GET/SETEX)
Parte 2: Fila de notificações (LPUSH + BRPOP)
Parte 3: Pub/Sub de atualizações de evento (PUBLISH/SUBSCRIBE)

Execução do Redis (Docker):
    docker run --name redis-local -p 6379:6379 -d redis

Uso (exemplos):
    # --- Parte 1 (Cache) ---
    python main.py cache get --id 101
    python main.py cache get --id 101 --show-ttl
    python main.py cache get --id 101 --ttl 10
    python main.py cache del --id 101

    # --- Parte 2 (Fila) ---
    # Terminal A (worker bloqueante):
    python main.py notify worker
    # Terminal B (produtor):
    python main.py notify enqueue --user "Leo" --message "Ingressos liberados"
    # Lote (JSON Lines com {"user": "...", "message":"..."} por linha):
    python main.py notify enqueue-batch --file msgs.jsonl

    # --- Parte 3 (Pub/Sub) ---
    # Terminal A (assinante):
    python main.py events subscribe
    # Terminal B (publicador de um evento existente no banco simulado):
    python main.py events publish --id 101

Variável de ambiente suportada:
    REDIS_URL (padrão: redis://localhost:6379/0)
"""

import os
import json
import logging
import argparse
from datetime import datetime, timezone
from typing import Tuple, Optional

import redis

DEFAULT_TTL = 60
QUEUE_KEY = "notificacao:fila"
PUBSUB_CHANNEL = "eventos:atualizacoes"

# --- "Fonte simulada" em memória (exigido pelo enunciado) --------------------
EVENTS_DB = {
    "101": {
        "event_id": "101",
        "titulo": "Tech Summit",
        "inicio": "2025-11-20T10:00:00Z",
        "local": "Pavilhão 1",
    },
    "102": {
        "event_id": "102",
        "titulo": "DataConf",
        "inicio": "2025-12-05T14:00:00Z",
        "local": "Auditório Central",
    },
    "103": {
        "event_id": "103",
        "titulo": "Live Coding Night",
        "inicio": "2025-12-12T19:30:00Z",
        "local": "Arena Dev",
    },
}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_redis_client() -> redis.Redis:
    """Cria cliente Redis a partir da env REDIS_URL, decodificando respostas."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(url, decode_responses=True)

# ===============================
# Parte 1 — Cache de Eventos
# ===============================

def get_event(event_id: str, r: Optional[redis.Redis] = None, ttl: int = DEFAULT_TTL) -> Tuple[Optional[dict], bool]:
    """
    Recupera dados de um evento com cache no Redis.
    - Tenta GET em event:<event_id>.
    - Se houver HIT, retorna (obj, True).
    - Se MISS, busca em EVENTS_DB, faz SETEX (ttl) e retorna (obj, False).
    - Se não existir na fonte, retorna (None, False).
    """
    if r is None:
        r = get_redis_client()

    key = f"event:{event_id}"
    cached = r.get(key)
    if cached is not None:
        logging.info("CACHE HIT -> %s", key)
        try:
            return json.loads(cached), True
        except json.JSONDecodeError:
            logging.warning("Valor no cache não é JSON válido; removendo e refazendo.")
            r.delete(key)  # sanear cache corrompido

    # MISS
    logging.info("CACHE MISS -> %s (buscando fonte simulada)", key)
    src = EVENTS_DB.get(event_id)
    if src is None:
        logging.warning("Evento %s não encontrado na fonte simulada.", event_id)
        return None, False

    # Grava no cache com SETEX
    r.setex(key, ttl, json.dumps(src, ensure_ascii=False))
    return src, False

def cmd_cache_get(args: argparse.Namespace) -> None:
    r = get_redis_client()
    try:
        data, hit = get_event(args.id, r=r, ttl=args.ttl)
    except redis.exceptions.ConnectionError as e:
        print(f"[ERRO] Não foi possível conectar ao Redis: {e}")
        print("Dica: suba o Redis com: docker run --name redis-local -p 6379:6379 -d redis")
        return

    if data is None:
        print(json.dumps({
            "event_id": args.id,
            "cache_hit": False,
            "found": False,
            "message": "Evento não encontrado na fonte simulada."
        }, ensure_ascii=False, indent=2))
        return

    output = {
        "event_id": args.id,
        "cache_hit": hit,
        "found": True,
        "data": data,
    }
    if hit and args.show_ttl:
        output["ttl_restante"] = r.ttl(f"event:{args.id}")

    print(json.dumps(output, ensure_ascii=False, indent=2))

def cmd_cache_del(args: argparse.Namespace) -> None:
    r = get_redis_client()
    key = f"event:{args.id}"
    try:
        removed = r.delete(key)
    except redis.exceptions.ConnectionError as e:
        print(f"[ERRO] Não foi possível conectar ao Redis: {e}")
        return
    status = "removida" if removed == 1 else "inexistente"
    print(json.dumps({"key": key, "status": status}, ensure_ascii=False, indent=2))

# ===============================
# Parte 2 — Fila de Notificações
# ===============================

def enqueue_notification(user: str, message: str, r: Optional[redis.Redis] = None) -> int:
    """
    Insere uma notificação na fila (lista Redis) usando LPUSH.
    Retorna o tamanho atual da fila.
    """
    if r is None:
        r = get_redis_client()

    payload = {
        "user": user,
        "message": message,
        "ts": now_iso(),
    }
    size = r.lpush(QUEUE_KEY, json.dumps(payload, ensure_ascii=False))
    logging.info("ENQUEUE -> %s (tamanho=%s)", payload, size)
    return size

def process_notifications(r: Optional[redis.Redis] = None) -> None:
    """
    Processa continuamente a fila com BRPOP (bloqueante).
    Ctrl+C para sair.
    """
    if r is None:
        r = get_redis_client()

    print(f"[worker] Aguardando notificações em '{QUEUE_KEY}' (Ctrl+C para sair)")
    try:
        while True:
            # BRPOP bloqueia até chegar item. Retorna (key, value)
            key, item = r.brpop(QUEUE_KEY, timeout=0)
            try:
                data = json.loads(item)
            except json.JSONDecodeError:
                print(f"[worker] Recebido item não-JSON: {item}")
                continue

            # Exibição simples
            print(json.dumps({
                "queue": key,
                "received_at": now_iso(),
                "notification": data
            }, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        print("\n[worker] Encerrando com segurança. Até mais!")

def cmd_notify_enqueue(args: argparse.Namespace) -> None:
    r = get_redis_client()
    try:
        size = enqueue_notification(args.user, args.message, r=r)
    except redis.exceptions.ConnectionError as e:
        print(f"[ERRO] Não foi possível conectar ao Redis: {e}")
        return
    print(json.dumps({
        "status": "enqueued",
        "queue": QUEUE_KEY,
        "size": size
    }, ensure_ascii=False, indent=2))

def cmd_notify_enqueue_batch(args: argparse.Namespace) -> None:
    r = get_redis_client()
    path = args.file
    if not os.path.exists(path):
        print(json.dumps({"error": f"Arquivo não encontrado: {path}"}, ensure_ascii=False, indent=2))
        return

    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(json.dumps({"warning": f"Linha inválida (ignorada): {line}"}, ensure_ascii=False))
                continue
            user = rec.get("user")
            message = rec.get("message")
            if not user or not message:
                print(json.dumps({"warning": f"Linha sem campos 'user'/'message' (ignorada): {line}"}, ensure_ascii=False))
                continue
            enqueue_notification(user, message, r=r)
            count += 1

    print(json.dumps({
        "status": "batch-enqueued",
        "queue": QUEUE_KEY,
        "count": count
    }, ensure_ascii=False, indent=2))

def cmd_notify_worker(args: argparse.Namespace) -> None:
    try:
        process_notifications()
    except redis.exceptions.ConnectionError as e:
        print(f"[ERRO] Não foi possível conectar ao Redis: {e}")

# ===============================
# Parte 3 — Pub/Sub
# ===============================

def publish_update(event_id: str, r: Optional[redis.Redis] = None) -> Optional[int]:
    """
    Publica atualização de evento no canal PUBSUB_CHANNEL.
    Mensagem contém: event_id, titulo e timestamp.
    Retorna número de assinantes que receberam (inteiro) ou None em caso de erro.
    """
    if r is None:
        r = get_redis_client()

    event, _ = get_event(event_id, r=r)  # reusa cache/fonte simulada
    if event is None:
        print(json.dumps({"error": f"Evento {event_id} não encontrado."}, ensure_ascii=False, indent=2))
        return None

    payload = {
        "event_id": event["event_id"],
        "titulo": event["titulo"],
        "ts": now_iso(),
    }
    receivers = r.publish(PUBSUB_CHANNEL, json.dumps(payload, ensure_ascii=False))
    logging.info("PUBLISH -> canal=%s, receivers=%s, payload=%s", PUBSUB_CHANNEL, receivers, payload)
    return receivers

def subscribe_updates(r: Optional[redis.Redis] = None) -> None:
    """
    Assina o canal PUBSUB_CHANNEL e imprime todas as mensagens recebidas.
    Ctrl+C para sair.
    """
    if r is None:
        r = get_redis_client()

    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(PUBSUB_CHANNEL)
    print(f"[subscriber] Inscrito em '{PUBSUB_CHANNEL}'. Aguardando mensagens... (Ctrl+C para sair)")

    try:
        for msg in pubsub.listen():
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            data_raw = msg.get("data")
            try:
                data = json.loads(data_raw)
            except (TypeError, json.JSONDecodeError):
                data = {"raw": data_raw}
            print(json.dumps({
                "channel": msg.get("channel"),
                "received_at": now_iso(),
                "message": data
            }, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        print("\n[subscriber] Encerrando assinatura. Até mais!")
    finally:
        try:
            pubsub.close()
        except Exception:
            pass

def cmd_events_publish(args: argparse.Namespace) -> None:
    r = get_redis_client()
    try:
        receivers = publish_update(args.id, r=r)
    except redis.exceptions.ConnectionError as e:
        print(f"[ERRO] Não foi possível conectar ao Redis: {e}")
        return
    if receivers is not None:
        print(json.dumps({
            "status": "published",
            "channel": PUBSUB_CHANNEL,
            "event_id": args.id,
            "receivers": receivers
        }, ensure_ascii=False, indent=2))

def cmd_events_subscribe(args: argparse.Namespace) -> None:
    try:
        subscribe_updates()
    except redis.exceptions.ConnectionError as e:
        print(f"[ERRO] Não foi possível conectar ao Redis: {e}")

# ===============================
# CLI
# ===============================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="redis-event-app — Partes 1 (Cache), 2 (Fila) e 3 (Pub/Sub)",
    )
    parser.add_argument("--log-level", default="INFO", help="Nível de log (DEBUG, INFO, WARNING, ERROR)")

    sub = parser.add_subparsers(dest="command", required=True)

    # Subcomando: cache
    p_cache = sub.add_parser("cache", help="Operações de cache de evento (GET/SETEX)")
    sub_cache = p_cache.add_subparsers(dest="cache_cmd", required=True)

    p_get = sub_cache.add_parser("get", help="Buscar evento (usa cache Redis com GET/SETEX)")
    p_get.add_argument("--id", required=True, help="ID do evento")
    p_get.add_argument("--ttl", type=int, default=DEFAULT_TTL, help=f"TTL do cache em segundos (padrão: {DEFAULT_TTL})")
    p_get.add_argument("--show-ttl", action="store_true", help="Exibe o TTL restante quando vier do cache (HIT)")
    p_get.set_defaults(func=cmd_cache_get)

    p_del = sub_cache.add_parser("del", help="Apagar chave do cache para um event_id")
    p_del.add_argument("--id", required=True, help="ID do evento")
    p_del.set_defaults(func=cmd_cache_del)

    # Subcomando: notify (fila)
    p_notify = sub.add_parser("notify", help="Fila de notificações (LPUSH/BRPOP)")
    sub_notify = p_notify.add_subparsers(dest="notify_cmd", required=True)

    p_enq = sub_notify.add_parser("enqueue", help="Enfileira uma notificação")
    p_enq.add_argument("--user", required=True, help="Nome do usuário")
    p_enq.add_argument("--message", required=True, help="Mensagem da notificação")
    p_enq.set_defaults(func=cmd_notify_enqueue)

    p_enq_batch = sub_notify.add_parser("enqueue-batch", help="Enfileira várias notificações de um arquivo JSON Lines")
    p_enq_batch.add_argument("--file", required=True, help="Caminho para arquivo .jsonl (um JSON por linha)")
    p_enq_batch.set_defaults(func=cmd_notify_enqueue_batch)

    p_worker = sub_notify.add_parser("worker", help="Processa a fila de forma bloqueante (BRPOP)")
    p_worker.set_defaults(func=cmd_notify_worker)

    # Subcomando: events (pub/sub)
    p_events = sub.add_parser("events", help="Pub/Sub de atualizações de evento")
    sub_events = p_events.add_subparsers(dest="events_cmd", required=True)

    p_pub = sub_events.add_parser("publish", help="Publica atualização no canal eventos:atualizacoes")
    p_pub.add_argument("--id", required=True, help="ID do evento a publicar")
    p_pub.set_defaults(func=cmd_events_publish)

    p_sub = sub_events.add_parser("subscribe", help="Assina o canal eventos:atualizacoes e imprime mensagens")
    p_sub.set_defaults(func=cmd_events_subscribe)

    return parser

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s: %(message)s")
    args.func(args)

if __name__ == "__main__":
    main()
