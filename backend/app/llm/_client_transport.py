
"""Transport resolution and initialization mixin for LLMClient."""

from typing import TYPE_CHECKING, Any, Optional

from openai import OpenAI

from ..config import Config
from ..contracts.provider_types import (
    ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED,
    PROVIDER_CLAUDE_CLI,
    PROVIDER_CODEX_CLI,
)
from ..utils.logger import get_logger
from ._client_shim import get_client_attr as _get_client_attr
from .providers.claude_cli import ClaudeCliClient
from .providers.codex_cli import CodexCliClient
from .providers.registry import openai_compat_base_url
from .transport_security import ensure_credentialed_transport_security

logger = get_logger("agora.llm_client")


class LLMClientTransportMixin:
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def _resolve_transport(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        timeout: float,
        resolved_provider_type: Optional[str],
        resolved_source: Optional[str],
        allow_api_key_fallback: bool,
    ) -> Optional[str]:
        """Setzt api_key/base_url/client/``_codex_cli_active`` (Issue #1405).

        codex_cli hat weder base_url noch api_key — beides ist fuer diesen
        Provider architektonisch bedeutungslos (Subprozess statt HTTP, lokale
        CLI-Login-Session statt Secret). Ausgelagert aus ``__init__``, damit
        die codex_cli-Fallunterscheidung nicht dessen radon-Komplexitäts-
        Budget sprengt (MAI-17-Gate).

        Gibt die ggf. aktualisierte ``api_key_source`` fuer das Audit-Log
        in ``__init__`` zurueck.
        """
        self._codex_cli_active = resolved_provider_type == PROVIDER_CODEX_CLI
        # claude_cli hat, anders als codex_cli, einen echten Secret (den per
        # ``claude setup-token`` erzeugten Langzeit-Token) — der laeuft durch
        # dieselbe Aufloesung wie jeder andere API-Key-Provider und landet
        # bereits im ``api_key``-Parameter, sobald diese Methode laeuft.
        # Nur base_url/Client-Wahl brauchen den eigenen Zweig.
        self._claude_cli_active = resolved_provider_type == PROVIDER_CLAUDE_CLI

        if api_key:
            self.api_key = api_key
            # resolved_source bleibt erhalten (passed_in oder vom Resolver)
        elif self._codex_cli_active:
            # Kein Secret vorgesehen — der Platzhalter geht nirgendwo hin,
            # er erfuellt nur die "ist ein Key gesetzt"-Invariante unten.
            self.api_key = "codex-cli-local-session"
            resolved_source = "local_cli_session"
        elif allow_api_key_fallback:
            self.api_key = Config.LLM_API_KEY
            if self.api_key:
                resolved_source = "config_fallback"
        else:
            self.api_key = None
        self.base_url = (
            None
            if (self._codex_cli_active or self._claude_cli_active)
            else (base_url or Config.LLM_BASE_URL)
        )

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        if self._codex_cli_active:
            # Issue #1405: kein OpenAI-SDK-Client — ``CodexCliClient`` ist ein
            # Duck-Type-Shim, der nur ``.chat.completions.create(**kwargs)``
            # nachbildet (die einzige Oberflaeche, die ``_provider_attempt``
            # tatsaechlich ruft) und intern ``codex exec`` als Subprozess
            # startet.
            self.client: "OpenAI | CodexCliClient | ClaudeCliClient" = _get_client_attr("CodexCliClient", CodexCliClient)()
            return resolved_source

        if self._claude_cli_active:
            # Analog zu codex_cli, aber ``ClaudeCliClient`` bekommt den
            # aufgeloesten Token direkt uebergeben statt ihn aus einer
            # ambienten Session zu lesen — siehe llm/providers/claude_cli.py.
            self.client = _get_client_attr("ClaudeCliClient", ClaudeCliClient)(oauth_token=self.api_key)
            return resolved_source

        # Issue #1103 (CWE-319): credential-behaftete Requests duerfen nicht
        # unverschluesselt an oeffentliche Hosts gehen. Muss vor dem
        # _get_client_attr("OpenAI", OpenAI)(...)-Client-Bau laufen, sonst geht der erste Request schon
        # unverschluesselt raus.
        ensure_credentialed_transport_security(self.base_url, self.api_key)
        # Issue #1284: Transport-Guard als zweite Verteidigungslinie hinter
        # der Routing-Validierung (``llm_profile_resolver.py``,
        # ``llm_routing_seed.py``). ``from_route()`` ist der einzige
        # produktive Konstruktionspfad fuer eine gerouteten Stage/Run-
        # Connection — jede persistierte oder wiederaufgenommene Route, die
        # die frueheren Gates umgangen hat (z. B. ein vor diesem Fix
        # gespeicherter ``stage_override``), landet spaetestens hier. Nutzt
        # ausschliesslich ``detect_provider`` (registry.py) — keine zweite
        # Heuristik.
        if self._detect_provider() == "anthropic":
            raise ValueError(ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED)
        # Issue #1072: ``self.base_url`` bleibt bewusst roh — Provider-
        # Detection (``_detect_provider``), das Invocation-Log und der native
        # Ollama-Pfad (``/api/chat``) haengen daran. Nur der OpenAI-SDK-Client
        # bekommt die auf den Compat-Pfad kanonisierte Form: Ollama-
        # Connections fuehren eine Base-URL ohne ``/v1``, ueber die
        # ``POST /chat/completions`` mit Plaintext ``404 page not found``
        # beantwortet wird.
        self.client = _get_client_attr("OpenAI", OpenAI)(
            api_key=self.api_key,
            base_url=openai_compat_base_url(self.base_url, self.model),
            timeout=timeout,
        )
        return resolved_source
