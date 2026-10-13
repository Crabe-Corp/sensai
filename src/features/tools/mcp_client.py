import json
import os
import queue
import shlex
import subprocess
import threading
from typing import Any
from pydantic import BaseModel, Field
from src.features.tools.registry import ToolDefinition, ToolRegistry


class MCPError(Exception):
    pass


class MCPConnectionError(MCPError):
    pass


class MCPTimeoutError(MCPError):
    pass


class MCPProtocolError(MCPError):
    def __init__(self, message: str, code: int | None = None, data: Any = None) -> None:
        """Initialise une exception d'erreur de protocole MCP avec code et données associées.
                PARAMS: - message - STR: le message d'erreur explicatif
                        - code - INT: code d'erreur JSON-RPC optionnel
                        - data - ANY: données contextuelles complémentaires
                RETURN: None"""
        super().__init__(message)
        self.code = code
        self.data = data


class MCPTool(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        alias="inputSchema",
    )

    model_config = {"populate_by_name": True}

    def to_tool_definition(self, client: "MCPClient") -> ToolDefinition:
        """Convertit l'outil MCP en ToolDefinition standard compatible avec le registre interne.
                PARAMS: - client - MCPCLIENT: instance du client MCP gérant l'appel réseau
                RETURN: instance ToolDefinition exécutable"""
        def handler(**kwargs: Any) -> Any:
            return client.call_tool(self.name, kwargs)

        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.input_schema,
            handler=handler,
        )


class MCPClient:
    def __init__(
        self,
        command: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        default_timeout: float = 15.0,
    ) -> None:
        """Initialise le client MCP avec la commande d'exécution du sous-processus serveur.
                PARAMS: - command - STR | LIST[STR]: commande de lancement du serveur MCP
                        - cwd - STR: répertoire de travail optionnel pour le sous-processus
                        - env - DICT[STR, STR]: variables d'environnement optionnelles
                        - default_timeout - FLOAT: délai d'attente maximal par défaut en secondes
                RETURN: None"""
        if isinstance(command, str):
            self.command = shlex.split(command, posix=False)
        else:
            self.command = list(command)
        self.cwd = cwd
        self.env = env
        self.default_timeout = default_timeout
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._pending_requests: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._next_request_id = 1
        self._is_running = False
        self._server_info: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        """Indique si le sous-processus du serveur MCP est actuellement actif et communicant.
                PARAMS: Aucun
                RETURN: booléen indiquant l'état de connexion"""
        return self._is_running and self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Démarre le sous-processus du serveur MCP, le thread d'écoute et effectue le handshake initial.
                PARAMS: Aucun
                RETURN: None"""
        if self.is_connected:
            return

        sub_env = dict(self.env if self.env is not None else os.environ)
        sub_env.setdefault("PYTHONIOENCODING", "utf-8")
        sub_env.setdefault("PYTHONUTF8", "1")

        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self.cwd,
                env=sub_env,
            )
        except OSError as exc:
            raise MCPConnectionError(
                f"Impossible de démarrer le serveur MCP via {' '.join(self.command)}: {exc}"
            ) from exc

        self._is_running = True
        self._reader_thread = threading.Thread(target=self._stdout_reader_loop, daemon=True)
        self._reader_thread.start()

        self._initialize_handshake()

    def _stdout_reader_loop(self) -> None:
        """Boucle de lecture asynchrone sur la sortie standard du serveur MCP dispatchant les réponses.
                PARAMS: Aucun
                RETURN: None"""
        if not self._process or not self._process.stdout:
            return

        while self._is_running:
            line = self._process.stdout.readline()
            if not line:
                break
            stripped = line.strip()
            if not stripped:
                continue

            try:
                msg = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            msg_id = msg.get("id")
            if msg_id is not None:
                with self._lock:
                    pending_queue = self._pending_requests.get(msg_id)
                if pending_queue:
                    pending_queue.put(msg)

        self._is_running = False

    def _send_rpc(self,
        method: str,
        params: dict[str, Any] | None = None,
        is_notification: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """Envoie un message JSON au serveur MCP et attend sa réponse si ce n'est pas une notification.
                PARAMS: - method - STR: le nom de la méthode JSON-RPC à invoquer
                        - params - DICT: paramètres optionnels de la requête
                        - is_notification - BOOL: vrai s'il s'agit d'une notification sans attente de retour
                        - timeout - FLOAT: délai d'attente personnalisé en secondes
                RETURN: résultat renvoyé par le serveur MCP ou None pour une notification"""
        if not self.is_connected or not self._process or not self._process.stdin:
            raise MCPConnectionError("Le serveur MCP n'est pas connecté.")

        req_timeout = timeout or self.default_timeout

        if is_notification:
            payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                payload["params"] = params
            serialized = json.dumps(payload, ensure_ascii=False) + "\n"
            try:
                self._process.stdin.write(serialized)
                self._process.stdin.flush()
            except OSError as exc:
                raise MCPConnectionError(f"Erreur d'écriture vers le serveur MCP: {exc}") from exc
            return None

        with self._lock:
            req_id = self._next_request_id
            self._next_request_id += 1
            resp_queue: queue.Queue[dict[str, Any]] = queue.Queue()
            self._pending_requests[req_id] = resp_queue

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        serialized = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            self._process.stdin.write(serialized)
            self._process.stdin.flush()
        except OSError as exc:
            with self._lock:
                self._pending_requests.pop(req_id, None)
            raise MCPConnectionError(f"Erreur d'écriture vers le serveur MCP: {exc}") from exc

        try:
            response = resp_queue.get(timeout=req_timeout)
        except queue.Empty as exc:
            raise MCPTimeoutError(
                f"Délai d'attente ({req_timeout}s) dépassé pour la méthode MCP '{method}'."
            ) from exc
        finally:
            with self._lock:
                self._pending_requests.pop(req_id, None)

        if "error" in response:
            err = response["error"]
            raise MCPProtocolError(
                message=err.get("message", "Erreur MCP indéterminée"),
                code=err.get("code"),
                data=err.get("data"),
            )

        return response.get("result", {})

    def _initialize_handshake(self) -> None:
        """Effectue le cycle d'initialisation standard MCP avec le serveur distant.
                PARAMS: Aucun
                RETURN: None"""
        init_result = self._send_rpc(
            "initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "sensai-agent", "version": "1.0.0"},
            },
        )
        self._server_info = init_result or {}
        self._send_rpc("notifications/initialized", is_notification=True)

    def list_tools(self, timeout: float | None = None) -> list[MCPTool]:
        """Interroge le serveur MCP pour obtenir la liste de tous les outils disponibles.
                PARAMS: - timeout - FLOAT: délai d'attente personnalisé en secondes
                RETURN: liste des objets MCPTool déclarés par le serveur"""
        result = self._send_rpc("tools/list", params={}, timeout=timeout) or {}
        raw_tools = result.get("tools", [])
        return [MCPTool.model_validate(t) for t in raw_tools]

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Exécute un outil spécifique sur le serveur MCP et extrait le résultat textuel ou JSON.
                PARAMS: - name - STR: le nom de l'outil à appeler
                        - arguments - DICT: dictionnaire des arguments de l'outil
                        - timeout - FLOAT: délai d'attente personnalisé en secondes
                RETURN: résultat retourné par l'outil distant"""
        result = (
            self._send_rpc(
                "tools/call",
                params={"name": name, "arguments": arguments or {}},
                timeout=timeout,
            )
            or {}
        )

        if result.get("isError"):
            error_msgs = []
            for item in result.get("content", []):
                if item.get("type") == "text":
                    raw_text = item.get("text", "")
                    try:
                        parsed = json.loads(raw_text)
                        if isinstance(parsed, dict) and "error" in parsed:
                            error_msgs.append(str(parsed["error"]))
                        else:
                            error_msgs.append(raw_text)
                    except Exception:
                        error_msgs.append(raw_text)
            error_str = " | ".join(error_msgs) if error_msgs else f"Échec de l'outil MCP '{name}'."
            raise MCPProtocolError(error_str)

        content_items = result.get("content", [])
        text_outputs: list[str] = []
        for item in content_items:
            if item.get("type") == "text":
                text_outputs.append(item.get("text", ""))

        joined_text = "\n".join(text_outputs)
        try:
            return json.loads(joined_text)
        except (json.JSONDecodeError, ValueError):
            return joined_text

    def register_into_registry(
        self,
        registry: ToolRegistry,
        prefix: str = "",
    ) -> list[ToolDefinition]:
        """Récupère les outils du serveur MCP et les enregistre dans le ToolRegistry spécifié.
                PARAMS: - registry - TOOLREGISTRY: le registre dans lequel enregistrer les outils
                        - prefix - STR: préfixe textuel optionnel à appliquer aux noms d'outils
                RETURN: liste des ToolDefinition nouvellement enregistrées"""
        tools = self.list_tools()
        registered: list[ToolDefinition] = []
        for tool_info in tools:
            tool_name = f"{prefix}{tool_info.name}" if prefix else tool_info.name
            tool_def = ToolDefinition(
                name=tool_name,
                description=tool_info.description,
                parameters=tool_info.input_schema,
                handler=lambda _name=tool_info.name, **kwargs: self.call_tool(_name, kwargs),
            )
            registry.register(tool_def)
            registered.append(tool_def)
        return registered

    def close(self) -> None:
        """Arrête le sous-processus serveur MCP et libère les ressources associées.
                PARAMS: Aucun
                RETURN: None"""
        self._is_running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    def __enter__(self) -> "MCPClient":
        """Démarre le client MCP dans le cadre d'un gestionnaire de contexte.
                PARAMS: Aucun
                RETURN: l'instance connectée de MCPClient"""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Ferme le client MCP à la sortie d'un bloc de contexte.
                PARAMS: - exc_type - ANY: type de l'exception levée
                        - exc_val - ANY: instance de l'exception
                        - exc_tb - ANY: traceback de l'exception
                RETURN: None"""
        self.close()
