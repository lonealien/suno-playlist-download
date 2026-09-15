#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
###### Suno Playlist Download (M4A) #####

Baixa apenas o formato original do Suno (.m4a), SEM conversão.
Rápido, sem ffmpeg, sem CPU extra.

Depois de baixar, use o `converter_mp3.bat` para converter as playlists
escolhidas para MP3.

-----
USAR COM O ARQUIVO .bat
Basta executar o SUNO_Download_Start.bat e seguir o que é pedido.

-----
USAR COM PYTHON:
Interativo:
    python download_suno.py

Linha de comando:
    python download_suno.py <url> [mais urls...] [opções]
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
import unicodedata
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL.*")

try:
    import requests
except ImportError:
    print("Dependência faltando: requests")
    print("Instale com:  pip install requests rich cryptography")
    sys.exit(3)

try:
    import base64
    import hashlib

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    print("Dependência faltando: cryptography")
    print("Instale com:  pip install requests rich cryptography")
    sys.exit(3)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("Dependência faltando: rich")
    print("Instale com:  pip install requests rich")
    sys.exit(3)


__version__ = "2.0.0"

API_PLAYLIST = "https://studio-api.prod.suno.com/api/playlist/{pid}"
API_RIGHTS = "https://studio-api.prod.suno.com/api/mango/rights"

PASTA_RAIZ = Path(__file__).resolve().parent / "Playlists"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://suno.com",
}

CHUNK_SIZE = 64 * 1024
CONNECT_TIMEOUT, READ_TIMEOUT = 15, 60
MAX_RETRIES = 3
RETRY_DELAYS = (5, 15, 30)

EXT_BY_TYPE = {
    "m4a-opus": ".m4a",
    "m4a": ".m4a",
    "mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "wav": ".wav",
    "mp4": ".mp4",
}


class BlockedError(Exception):
    """O Suno recusou uma requisição (403/429) — para tudo por segurança."""


class PlaylistNotFoundError(Exception):
    """O link da playlist está errado ou a playlist não é pública."""


# --------------------------------------------------------------------------- #
#  Auxiliares
# --------------------------------------------------------------------------- #

def extract_playlist_id(text: str) -> str:
    text = text.strip()
    m = re.search(r"suno\.com/playlist/([0-9a-fA-F-]{30,40})", text)
    if m:
        return m.group(1).strip("/? ")
    m = re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                     r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text)
    if m:
        return text.lower()
    raise ValueError("não é um link de playlist do Suno")


def sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", str(name or ""))
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "sem_titulo"


def human_duration(seconds) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "?"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


# --------------------------------------------------------------------------- #
#  API do Suno
# --------------------------------------------------------------------------- #

def make_session(proxy: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    return s


def _get_json(session: requests.Session, url: str, referer: str) -> dict:
    headers = {"Referer": referer}
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            if r.status_code in (403, 429):
                raise BlockedError(f"HTTP {r.status_code} ao contatar o Suno")
            if r.status_code == 404:
                raise PlaylistNotFoundError(url)
            r.raise_for_status()
            return r.json()
        except BlockedError:
            raise
        except PlaylistNotFoundError:
            raise
        except (requests.RequestException, ValueError) as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
    raise RuntimeError(f"requisição falhou após {MAX_RETRIES} tentativas: {last_err}")


def fetch_playlist(session: requests.Session, pid: str) -> dict:
    referer = f"https://suno.com/playlist/{pid}"
    entries: list = []
    seen: set = set()
    meta: dict = {}
    page = 1
    while page <= 20:
        data = _get_json(session, API_PLAYLIST.format(pid=pid) + f"?page={page}", referer)
        meta = {k: v for k, v in data.items() if not isinstance(v, list)}
        batch = data.get("playlist_clips") or []
        new = 0
        for item in batch:
            if not isinstance(item, dict):
                continue
            clip = item.get("clip")
            if isinstance(clip, dict) and clip.get("id") and clip["id"] not in seen:
                seen.add(clip["id"])
                pos = item.get("relative_index")
                if not isinstance(pos, (int, float)):
                    pos = len(entries) + 1
                entries.append((pos, clip))
                new += 1
        total = data.get("num_total_results") or len(entries)
        if new == 0 or len(entries) >= total:
            break
        page += 1
    entries.sort(key=lambda pc: pc[0])
    meta["clips"] = [clip for _, clip in entries]
    return meta


def pick_media(clip: dict):
    for m in clip.get("media_urls") or []:
        url = m.get("url")
        if not url:
            continue
        ctype = (m.get("content_type") or "").lower()
        delivery = (m.get("delivery") or "").lower()
        if delivery and delivery != "progressive":
            continue
        if ctype.startswith("video") or ctype == "mp4":
            continue
        ext = EXT_BY_TYPE.get(ctype)
        if ext is None:
            ext = Path(url.split("?")[0]).suffix or ".m4a"
        return url, ext
    return None, None


# --------------------------------------------------------------------------- #
#  Descriptografia ("Mango")
# --------------------------------------------------------------------------- #

def fetch_rights(session: requests.Session, clip_id: str) -> dict:
    body = {"content_params": {"content_id": clip_id, "content_type": "clip"}}
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = session.post(API_RIGHTS, json=body,
                             timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            if r.status_code in (403, 429):
                raise BlockedError(f"HTTP {r.status_code} do servidor de direitos")
            r.raise_for_status()
            data = r.json()
            if not (data.get("key") and data.get("iv") and data.get("glt")):
                raise RuntimeError("resposta de direitos incompleta")
            return data
        except BlockedError:
            raise
        except (requests.RequestException, ValueError) as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
    raise RuntimeError(f"requisição de direitos falhou após {MAX_RETRIES} tentativas: {last_err}")


def _unwrap(wrapped_b64: str, clip_id: str, user_key: bytes) -> bytes:
    w = base64.b64decode(wrapped_b64)
    nonce, ct, tag = w[:12], w[12:-16], w[-16:]
    dec = Cipher(algorithms.AES(user_key), modes.GCM(nonce, tag)).decryptor()
    dec.authenticate_additional_data(clip_id.encode())
    return dec.update(ct) + dec.finalize()


def decrypt_bytes(data: bytes, clip_id: str, rights: dict) -> bytes:
    user_key = hashlib.sha256(rights["glt"].encode()).digest()
    key = _unwrap(rights["key"], clip_id, user_key)
    counter = _unwrap(rights["iv"], clip_id, user_key)
    dec = Cipher(algorithms.AES(key), modes.CTR(counter)).decryptor()
    return dec.update(data) + dec.finalize()


def is_playable_audio(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
    except OSError:
        return False
    if head[4:8] == b"ftyp":
        return True
    if head[:4] == bytes([0x1A, 0x45, 0xDF, 0xA3]):
        return True
    if head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return True
    return False


def bytes_are_audio(data: bytes) -> bool:
    if len(data) < 12:
        return False
    head = data[:12]
    if head[4:8] == b"ftyp":
        return True
    if head[:4] == bytes([0x1A, 0x45, 0xDF, 0xA3]):
        return True
    if head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return True
    return False


def download_file(session: requests.Session, url: str, dest: Path,
                  referer: str, progress: Progress, task_id) -> Path:
    tmp = dest.with_suffix(dest.suffix + ".part")
    headers = {"Referer": referer}
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            with session.get(url, headers=headers, stream=True,
                             timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)) as r:
                if r.status_code in (403, 429):
                    raise BlockedError(f"HTTP {r.status_code} do servidor de arquivos")
                r.raise_for_status()
                total = int(r.headers.get("Content-Length") or 0) or None
                progress.update(task_id, total=total, completed=0)
                done = 0
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            fh.write(chunk)
                            done += len(chunk)
                            progress.update(task_id, completed=done)
            tmp.replace(dest)
            return dest
        except BlockedError:
            raise
        except requests.RequestException as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
    raise RuntimeError(f"download falhou após {MAX_RETRIES} tentativas: {last_err}")


# --------------------------------------------------------------------------- #
#  Interface
# --------------------------------------------------------------------------- #

def banner(console: Console) -> None:
    console.print(Panel.fit(
        f"[bold]Download Playlists SUNO (M4A) [/]  v{__version__}\n"
        "[dim]Baixe faixas de playlists públicas do SUNO — sem limites.[/]\n"
        "[dim]Formato de saída: M4A (original do Suno, sem conversão).[/]\n"
        "[dim]Depois use o 'converter_mp3.bat' para converter para MP3.[/]\n"
        "[bright_black]by: Lonne Alien[/]\n"
        "[bold]«IDFC!»[/]",
        border_style="bright_magenta"))


def summary_table(results: list, playlist_name: str) -> Table:
    table = Table(title=f"{playlist_name} — resultados", header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Faixa", overflow="ellipsis", max_width=46)
    table.add_column("Status")
    table.add_column("Tamanho", justify="right")
    for row in results:
        num, title, status, size = row
        style = {"downloaded": "green", "decrypted": "green",
                 "skipped": "dim", "failed": "red", "unavailable": "yellow"}.get(status, "")
        table.add_row(str(num), Text(title), Text(status, style=style), size)
    return table


# --------------------------------------------------------------------------- #
#  Principal
# --------------------------------------------------------------------------- #

def process_playlist(pid: str, args, console: Console) -> int:
    with console.status("Buscando informações da playlist…"):
        try:
            meta = fetch_playlist(make_session(args.proxy), pid)
        except PlaylistNotFoundError:
            console.print(Panel(
                "[red]Playlist não encontrada.[/] Verifique se o link está correto e "
                "se a playlist é [bold]pública[/] (no Suno: playlist → ⋯ → Tornar Pública).",
                title=f"suno.com/playlist/{pid}"))
            return 1
        except BlockedError:
            _print_blocked(console)
            return 2

    clips = meta.get("clips") or []
    name = sanitize_filename(meta.get("name") or pid)
    byline = (meta.get("user_display_name") or "").strip()
    handle = (meta.get("user_handle") or "").strip()
    if handle and not handle.startswith("@"):
        handle = "@" + handle

    if not clips:
        console.print(f"[yellow]A playlist '{name}' está vazia — nada para baixar.[/]")
        return 0

    if args.out:
        outdir = Path(args.out) / name
    else:
        outdir = PASTA_RAIZ / name
    outdir.mkdir(parents=True, exist_ok=True)

    console.print()
    console.print(f"  [bold]{name}[/] "
                  f"[dim]por {byline} {handle} — {len(clips)} faixas, "
                  f"{human_duration(meta.get('total_duration'))} no total[/]")
    console.print(f"  salvando em  [underline]{outdir.resolve()}[/]\n")

    delay_base = max(0.0, args.delay)
    results = []
    failed = 0
    width = len(str(len(clips)))

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    overall = progress.add_task("[bold]geral[/]", total=len(clips))

    blocked = False
    with progress:
        for i, clip in enumerate(clips, 1):
            title = (clip.get("title") or clip.get("id") or "sem_titulo").strip()
            url, ext = pick_media(clip)
            num = str(i).zfill(width)
            if not url:
                progress.advance(overall)
                results.append((num, title, "unavailable", "—"))
                console.print(f"  [yellow]⚠ {num} — {title}: nenhum arquivo de áudio "
                              "disponível (pulado)[/]")
                continue

            dest = outdir / f"{num} - {sanitize_filename(title)}{ext}"

            if dest.exists() and not args.overwrite:
                if is_playable_audio(dest):
                    progress.advance(overall)
                    size = human_size(dest.stat().st_size)
                    results.append((num, title, "skipped", size))
                    continue
                # Arquivo existe mas ainda está criptografado — descriptografa no lugar
                desc = f"{num} · {title} (descriptografando)"
                fix_task = progress.add_task(desc[:52], total=None)
                try:
                    rights = fetch_rights(make_session(args.proxy), clip.get("id"))
                    blob = decrypt_bytes(dest.read_bytes(), clip.get("id"), rights)
                    if not bytes_are_audio(blob):
                        raise RuntimeError("arquivo descriptografado ainda inválido")
                    dest.write_bytes(blob)
                    size = human_size(dest.stat().st_size)
                    results.append((num, title, "decrypted", size))
                except (BlockedError, RuntimeError, ValueError) as e:
                    if isinstance(e, BlockedError):
                        progress.remove_task(fix_task)
                        blocked = True
                        break
                    failed += 1
                    results.append((num, title, "failed", "—"))
                    console.print(f"\n[red]✗ {num} — {title}: {e}[/]")
                finally:
                    try:
                        progress.remove_task(fix_task)
                    except Exception:
                        pass
                    progress.advance(overall)
                if i < len(clips):
                    time.sleep(delay_base + random.uniform(0, delay_base))
                continue

            desc = f"{num} · {title}"
            if len(desc) > 52:
                desc = desc[:49] + "…"
            file_task = progress.add_task(desc, total=None)
            try:
                download_file(make_session(args.proxy), url, dest,
                              f"https://suno.com/playlist/{pid}",
                              progress, file_task)
                rights = fetch_rights(make_session(args.proxy), clip.get("id"))
                blob = decrypt_bytes(dest.read_bytes(), clip.get("id"), rights)
                if not bytes_are_audio(blob):
                    raise RuntimeError("arquivo descriptografado não tem cabeçalho de áudio")
                dest.write_bytes(blob)
                size = human_size(dest.stat().st_size)
                results.append((num, title, "downloaded", size))
            except BlockedError:
                progress.remove_task(file_task)
                blocked = True
                break
            except RuntimeError as e:
                failed += 1
                results.append((num, title, "failed", "—"))
                console.print(f"\n[red]✗ {num} — {title}: {e}[/]")
            finally:
                try:
                    progress.remove_task(file_task)
                except Exception:
                    pass
                progress.advance(overall)
            if i < len(clips):
                time.sleep(delay_base + random.uniform(0, delay_base))

    console.print()
    console.print(summary_table(results, name))
    downloaded = sum(1 for r in results if r[2] in ("downloaded", "decrypted"))
    skipped = sum(1 for r in results if r[2] == "skipped")
    console.print(
        f"\n  [green]{downloaded} baixadas[/] · [dim]{skipped} já no disco[/]"
        f" · [red]{failed} falharam[/]   →  [underline]{outdir.resolve()}[/]")
    console.print(
        "  [bright_black]Download Completo!!! Obrigado!!!!![/]\n")
    if blocked:
        _print_blocked(console)
        return 2
    return 1 if failed else 0


def _print_blocked(console: Console) -> None:
    console.print(Panel(
        "[bold red]O Suno recusou a conexão (403/429).[/]\n"
        "A ferramenta parou imediatamente para manter sua conexão segura.\n"
        "Espere algumas horas e tente de novo, rode com menos links por vez, ou "
        "roteie pela sua VPN:\n"
        "[dim]    python download_suno.py <link> --proxy socks5://127.0.0.1:1080[/]",
        title="Descansar é mais seguro", border_style="red"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="download_suno",
        description="Baixa todas as faixas de playlists públicas do Suno — "
                    "em formato M4A (original, sem conversão).",
        epilog="by Lonne Alien — «IDFC!»")
    parser.add_argument("urls", nargs="*",
                        help="link(s) ou id(s) da(s) playlist(s)")
    parser.add_argument("--out", metavar="DIR",
                        help="pasta de saída (padrão: Playlists/<playlist>)")
    parser.add_argument("--delay", type=float, default=1.0, metavar="SEG",
                        help="pausa base entre downloads em segundos "
                             "(aleatoriamente 1–2× isso; padrão 1)")
    parser.add_argument("--overwrite", action="store_true",
                        help="rebaixar faixas que já existem no disco")
    parser.add_argument("--proxy", metavar="URL",
                        help="roteia todo o tráfego por um proxy/VPN, ex.: "
                             "socks5://127.0.0.1:1080 ou http://host:8080")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    console = Console()
    banner(console)

    if args.urls:
        pids = []
        for u in args.urls:
            try:
                pids.append(extract_playlist_id(u))
            except ValueError:
                console.print(f"[red]'{u}' não é um link de playlist do Suno — pulando.[/]")
        if not pids:
            console.print("[dim]Nenhuma playlist válida informada — tchau![/]")
            return 0
        worst = 0
        for n, pid in enumerate(pids):
            if n:
                console.print("\n[dim]— próxima playlist —[/]\n")
            worst = max(worst, process_playlist(pid, args, console))
        return worst

    console.print(
        "Cole o link da playlist do Suno e pressione [bold]ENTER[/].\n"
        "Digite [bold]'sair'[/] a qualquer momento para encerrar.\n")

    while True:
        try:
            line = console.input("[bold cyan]🔗 Link da playlist> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n👋 Encerrando.")
            break

        if not line:
            console.print("[yellow]Nada digitado — cole o link ou digite 'sair'.[/]\n")
            continue
        if line.lower() in ("sair", "exit", "quit", "q"):
            console.print("👋 Encerrando.")
            break

        try:
            pid = extract_playlist_id(line)
        except ValueError:
            console.print("[red]✗ Isso não parece um link de playlist do Suno. "
                          "Tente de novo.[/]\n")
            continue

        try:
            process_playlist(pid, args, console)
        except Exception as e:
            console.print(f"[red]✗ Erro inesperado: {e}[/]\n")

        try:
            resp = console.input(
                "\nBaixar outra playlist? ([bold]s[/]/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n👋 Encerrando.")
            break
        if resp not in ("s", "sim", "y", "yes"):
            console.print("👋 Encerrando.")
            break
        console.print()

    if not os.environ.get("SUNODL_NO_PAUSE") and not sys.stdin.isatty():
        try:
            input("\nAperte Enter para fechar…")
        except (EOFError, KeyboardInterrupt):
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrompido — as faixas já finalizadas continuam no disco. Tchau!")
        sys.exit(130)
