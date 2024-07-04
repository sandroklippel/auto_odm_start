#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# MIT License

# Copyright (c) 2024 Sandro Klippel

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

""" Automatically processes a set of drone image files from a monitored directory using a NodeODM server.
"""

import os
import time
import sys
import json
import argparse
import signal
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pyodm import Node
from pyodm.types import TaskStatus
from pyodm.exceptions import NodeConnectionError, NodeResponseError, TaskFailedError
from threading import Thread, Event

__author__ = "Sandro Klippel"
__copyright__ = "Copyright 2024, Sandro Klippel"
__license__ = "MIT"
__version__ = "0.0.1"
__maintainer__ = "Sandro Klippel"
__email__ = "sandroklippel at gmail.com"
__status__ = "Prototype"
__revision__ = "$Format:%H$"

TIME_WAIT = 3
task_running_list = []  # uuid list – Unique identifier of the task
shutdown = False


def shutdown_handler(signum, frame):
    global shutdown
    shutdown = True


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


class TokenFileHandler(FileSystemEventHandler):

    def __init__(self, tokens, action):
        super().__init__()
        self.tokens = tokens
        self.action = action

    def _parsetk(self, str_path):
        # token
        return os.path.splitext(os.path.basename(str_path))[0].lower()

    def _parsedn(self, str_path):
        # directory name
        return os.path.dirname(str_path)

    def _parseds(self, dn):
        # dataset name
        return os.path.basename(dn)

    def on_created(self, event):
        # criação de um arquivo
        if not event.is_directory:
            tk = self._parsetk(event.src_path)
            if tk in self.tokens:
                dn = self._parsedn(event.src_path)
                ds = self._parseds(dn)
                self.action(dn, ds, tk)

    def on_moved(self, event):
        # arquivo foi renomeado (movimentado)
        if not event.is_directory:
            dn = self._parsedn(event.dest_path)
            src_dn = self._parsedn(event.src_path)
            if dn == src_dn:  # mesmo diretório, arquivo foi renomeado
                tk = self._parsetk(event.dest_path)
                if tk in self.tokens:
                    ds = self._parseds(dn)
                    self.action(dn, ds, tk)


def read_config(s):
    try:
        with open(s, "r") as jsonfile:
            return json.load(jsonfile)
    except json.JSONDecodeError:
        logging.error("Invalid config file")
        sys.exit(1)
    except FileNotFoundError:
        logging.error("The file {} was not found".format(s))
        sys.exit(1)


def lista_arquivos_jpg(diretorio):
    """
    Returns a list of JPG files in a directory, with relative paths.

    Args:
        diretorio (str): The path to the directory.

    Returns:
        list: list with the relative paths of the JPG files.
    """

    arquivos_jpg = []
    for nome_arquivo in os.listdir(diretorio):
        caminho_completo = os.path.join(diretorio, nome_arquivo)
        if os.path.isfile(caminho_completo) and nome_arquivo.lower().endswith(".jpg"):
            arquivos_jpg.append(os.path.relpath(caminho_completo, start=os.curdir))
    return arquivos_jpg


def is_valid_dir(output_dir):
    """
    Checks if the output directory is valid.

    Args:
        output_dir (str): The path to the output directory.

    Returns:
        bool: True if the directory is valid (exists, is a directory and has write permission), False otherwise.
    """
    return (
        os.path.isabs(output_dir)
        and os.path.isdir(output_dir)
        and os.access(output_dir, os.W_OK)
    )


def read_options_from_preset(p, t):
    s = os.path.join(p, t + ".preset")
    with open(s, "r") as jsonfile:
        return json.load(jsonfile)


def write_status(dn, task_uuid_or_last_error, task_status="RUNNING"):
    fn = os.path.join(dn, f"TASK_{task_status}")
    with open(fn, "w") as fd:
        print(task_uuid_or_last_error, file=fd)
    os.chmod(fn, 0o777)


def remove_token_file(dn, fn="TASK_RUNNING"):
    try:
        os.remove(os.path.join(dn, fn))
    except FileNotFoundError:
        pass


def run_task(task, completed):
    try:
        i = task.info()
        task_running_list.append(i.uuid)
        task.wait_for_completion(interval=TIME_WAIT)
    except TaskFailedError as e:
        logging.error("Task Error: {}".format(e))
    except Exception as e:
        logging.error("Unexpected Error: {}".format(e))
    finally:
        try:
            task_running_list.remove(i.uuid)
        except ValueError:
            pass
        completed.set()


def download_assets(task, completed, destination, dn):
    completed.wait()
    try:
        i = task.info()
        if i.status == TaskStatus.COMPLETED:
            fnzip = task.download_zip(destination)
            new_fnzip = fnzip.replace(i.uuid, i.name)
            os.rename(fnzip, new_fnzip)
            write_status(dn, new_fnzip, "DOWNLOAD_COMPLETED")
        elif i.status == TaskStatus.FAILED:
            write_status(dn, i.last_error, "FAILED")
        elif i.status == TaskStatus.CANCELED:
            write_status(dn, i.uuid, "CANCELED")
        else:
            task.cancel()  # removes orphaned tasks (without a thread)
            write_status(dn, i.uuid, "CANCELED")
    except TaskFailedError as e:
        logging.error("Task Error: {}".format(e))
        write_status(dn, e, "FAILED")
    except Exception as e:
        logging.error("Unexpected Error: {}".format(e))
        write_status(dn, e, "FAILED")
    remove_token_file(dn)


def starts_threads(dn, ds, tk, presets_dir, outdir, node):
    arquivos_jpg = lista_arquivos_jpg(dn)
    if not arquivos_jpg:
        return

    task_options = read_options_from_preset(presets_dir, tk)

    try:
        task = node.create_task(files=arquivos_jpg, name=ds, options=task_options)
        i = task.info()
    except Exception as e:
        logging.error("Unexpected error uploading files: {}".format(e))
        write_status(dn, e, "UPLOAD_FAILED")
        remove_token_file(dn, tk)
        return

    completed = Event()

    run_task_thread = Thread(target=run_task, args=(task, completed))
    run_task_thread.start()
    write_status(dn, i.uuid)
    remove_token_file(dn, tk)

    download_assets_thread = Thread(
        target=download_assets, args=(task, completed, outdir, dn)
    )
    download_assets_thread.start()


def cancel_all_pending_tasks(n, l):
    logging.info("Shutting down, about to cancel all running tasks")
    for uuid in l:
        try:
            t = n.get_task(uuid)
            t.cancel()
        except Exception:
            logging.error("Error canceling the task {}".format(uuid))
        time.sleep(TIME_WAIT)  # delay to threads close


def cli():
    parser = argparse.ArgumentParser(
        description="Automatically processes a set of drone image files from a monitored directory using a NodeODM server.",
        epilog=__copyright__,
    )
    parser.add_argument(
        "--config",
        dest="config_fn",
        metavar="file",
        required=True,
        type=str,
        help="json config file",
    )
    parser.add_argument("--version", action="version", version=__version__)

    args = parser.parse_args()
    return args.config_fn


def auto_odm_start():
    """monitors and starts an odm task"""

    settings = read_config(cli())

    path_to_watch = settings["path_to_watch"]
    presets_dir = settings["presets_dir"]
    outdir = settings["outdir"]
    server = settings["server"]
    port = settings["port"]
    odm_token = settings["odm_token"]

    if not is_valid_dir(outdir):
        logging.error("Output directory invalid.")
        return 1

    tokens = [
        os.path.splitext(t)[0] for t in os.listdir(presets_dir) if t.endswith(".preset")
    ]

    if not tokens:
        logging.error("No tokens found.")
        return 1

    node = Node(host=server, port=port, token=odm_token)

    try:
        info = node.info()

    except NodeConnectionError as e:
        logging.error("Cannot connect: {}".format(e))
        return 1

    except NodeResponseError as e:
        logging.error("Node error: {}".format(e))
        return 1

    logging.info(
        f"""
            Server: {server}:{port}
            Engine: {info.engine} {info.version}
            Max images: {info.max_images}
            Max parallel tasks: {info.max_parallel_tasks}
            """
    )

    token_handler = TokenFileHandler(
        tokens=tokens,
        action=lambda dn, ds, tk: starts_threads(dn, ds, tk, presets_dir, outdir, node),
    )
    observer = Observer()
    observer.schedule(token_handler, path_to_watch, recursive=True)
    observer.start()

    while not shutdown:
        time.sleep(TIME_WAIT)

    observer.stop()
    observer.join()
    cancel_all_pending_tasks(node, task_running_list.copy())
    return 0


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sys.exit(auto_odm_start())
