"""CollectionContext — fonte única de verdade do contexto operacional de uma
coleta (manufacturer/vehicle_model/market), e único ponto de normalização
canônica desses três campos em todo o projeto (004 — correção de achado do
Codex sobre a generalização multi-modelo introduzida em 002).

Por que existe: antes desta feature, `run_collection_driver()`/
`process_capture()` recebiam manufacturer/vehicle_model separados do
`run_id`, com defaults que mascaravam a ausência do valor real e nenhuma
validação contra o `CollectionRun.scope` já persistido — um call site podia
(por engano ou esquecimento) processar/persistir conteúdo de um modelo sob o
scope de outro. `CollectionContext` substitui essa passagem solta de
parâmetros por uma única estrutura tipada, imutável e validada na
construção; `build_scope`/`parse_scope` formam um round-trip determinístico
e sem ambiguidade de concatenação (nenhum componente pode conter o
delimitador do scope).

`normalize_scope_component()` é a ÚNICA regra de normalização canônica para
manufacturer/vehicle_model/market usada nos pontos operacionais deste
projeto (CLI, scope, URL do índice de mercado, atribuição de identidade na
descoberta MARKET_INDEX, run completion). `list_by_scope()`
(persistence/repositories/spec_registry_repo.py) e as funções de scope de
analysis/comparison.py e analysis/redundancy.py (003) já implementavam, de
forma independente, uma regra equivalente (`strip().upper()`) para qualquer
valor que passe por esta normalização — não foram alteradas (Constitution:
preservar feature 003 intacta); a equivalência é estrutural, não uma
migração pendente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from amayama_scraper.domain.identity import SpecIdentity

#: Fonte atribuída ao projeto inteiro (Constitution §2) — nunca escolhida
#: pelo operador, mas normalizada pela mesma regra por consistência.
SOURCE = "AMAYAMA"

_DELIMITER = ":"

#: Letras, dígitos e hífens simples internos — nunca vazio, nunca o
#: delimitador do scope (":"), nunca caracteres inseguros de path de URL
#: ("/", "\\", "..", "?", "#"). Cobre todo manufacturer/vehicle_model/market
#: Volkswagen/Amayama real observado (ex.: "AMA-BR", "T-CROSS") e garante,
#: por construção, que a forma canônica e sua forma de URL (apenas
#: lower()) nunca colidem entre dois valores distintos.
_COMPONENT_PATTERN = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")


class InvalidScopeComponentError(ValueError):
    """Componente de scope vazio, com o delimitador do scope, ou com
    caractere fora do alfabeto canônico (letras/dígitos/hífen simples)."""


class InvalidScopeError(ValueError):
    """String de scope não decompõe em exatamente 4 componentes válidos."""


class ContextScopeMismatchError(ValueError):
    """CollectionContext fornecido diverge do CollectionRun.scope persistido.

    Nunca deve ser capturado silenciosamente — sinaliza que algum call site
    passou (ou esqueceu de passar) o contexto errado para uma coleta já
    associada a outro modelo/mercado (004 — achado do Codex)."""


class CaptureRunMismatchError(ValueError):
    """`capture_input.run_id` difere do `run_id` sob o qual `process_capture()`
    foi chamado (004, achado final do Codex — hardening de provenance).

    `process_capture()` valida contexto/spec_key contra `run_id`, mas
    `accept_capture()` persiste o raw usando `capture_input.run_id` — sem
    esta checagem, os dois poderiam divergir (ex.: run_id de GOL passado ao
    validador, mas `capture_input.run_id` de um run da Amarok usado na
    persistência), quebrando a garantia de que tudo que foi validado é
    exatamente o que é persistido. Falha fechada, antes de `accept_capture()`."""


class UnregisteredSpecIdentityError(ValueError):
    """`spec_key` sem `SpecIdentity` correspondente em `spec_registry` (004,
    hardening final).

    Falha fechada: nenhum caminho operacional que processe/persista sob um
    `spec_key` pode prosseguir sem confirmar, por uma `SpecIdentity`
    efetivamente registrada, que ele pertence ao `CollectionContext` da
    coleta corrente. "Identidade ausente" nunca é tratada como "nada a
    validar, prossiga" — em operação real, todo `spec_key` chega a
    SPEC_NAVIGATION/GROUP_DETAIL/finalização já registrado via MARKET_INDEX;
    um `spec_key` não registrado é sempre um erro de programação ou dado
    corrompido, nunca um caso legítimo a ignorar."""


def normalize_scope_component(value: str, *, field_name: str) -> str:
    """Regra canônica ÚNICA: trim -> rejeita não-ASCII -> upper -> valida
    alfabeto -> rejeita vazio.

    `" GOL "` e `"GOL"` normalizam para o mesmo componente (`"GOL"`) —
    nunca representam dois contextos diferentes.

    A rejeição de não-ASCII acontece ANTES de `.upper()` deliberadamente
    (004, correção de achado do Codex): `str.upper()` do Python pode
    *expandir* alguns caracteres Unicode em múltiplos caracteres ASCII —
    `"ß".upper() == "SS"`, `"ﬀ".upper() == "FF"` — o que faria dois valores
    de entrada diferentes ("ß" e "SS", por exemplo) colidirem no mesmo
    componente canônico se o alfabeto fosse validado só depois do
    `.upper()`. Rejeitar qualquer caractere fora de ASCII antes de qualquer
    transformação de case elimina essa classe de colisão por completo —
    nunca há transliteração/normalização silenciosa de Unicode.
    """
    trimmed = value.strip()
    if not trimmed.isascii():
        raise InvalidScopeComponentError(
            f"{field_name}={value!r} contains non-ASCII character(s) — rejected "
            "before any case normalization (never transliterated: inputs like "
            "'ß' or 'ﬀ' are refused outright, never silently turned into 'SS'/'FF')"
        )
    normalized = trimmed.upper()
    if not normalized or not _COMPONENT_PATTERN.fullmatch(normalized):
        raise InvalidScopeComponentError(
            f"{field_name}={value!r} is not a valid scope component "
            f"(normalized={normalized!r}) — only ASCII letters, digits and single "
            "internal hyphens are allowed, never empty, never containing "
            "':' or URL-unsafe characters"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class CollectionContext:
    """Contexto operacional único de uma coleta — manufacturer/vehicle_model/
    market (+ source), sempre normalizados e validados na construção.

    Nenhum default oculto: quem constrói precisa fornecer manufacturer/
    vehicle_model/market explicitamente — funções internas de execução
    (process_capture/run_collection_driver) exigem esta estrutura sem
    fallback, para que nunca seja possível "esquecer" o contexto e cair
    silenciosamente em um valor mascarante.
    """

    manufacturer: str
    vehicle_model: str
    market: str
    source: str = SOURCE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "manufacturer",
            normalize_scope_component(self.manufacturer, field_name="manufacturer"),
        )
        object.__setattr__(
            self,
            "vehicle_model",
            normalize_scope_component(self.vehicle_model, field_name="vehicle_model"),
        )
        object.__setattr__(
            self, "market", normalize_scope_component(self.market, field_name="market")
        )
        object.__setattr__(
            self, "source", normalize_scope_component(self.source, field_name="source")
        )

    def scope(self) -> str:
        return build_scope(self)


def build_scope(context: CollectionContext) -> str:
    """Serializa CollectionContext -> string de scope, sem concatenação
    ambígua: cada componente é garantido, pela validação de
    CollectionContext, a nunca conter o delimitador (':') — o split em
    parse_scope() é portanto sempre não-ambíguo e reversível (nenhuma
    combinação diferente de componentes pode colidir na mesma string)."""
    return _DELIMITER.join(
        (context.source, context.manufacturer, context.vehicle_model, context.market)
    )


def parse_scope(scope: str) -> CollectionContext:
    """Inverso de build_scope() — recupera o CollectionContext canônico a
    partir de um CollectionRun.scope persistido. Round-trip garantido:
    parse_scope(build_scope(ctx)) == ctx para todo CollectionContext válido.
    """
    parts = scope.split(_DELIMITER)
    if len(parts) != 4:
        raise InvalidScopeError(
            f"scope {scope!r} does not decompose into exactly 4 ':'-separated "
            f"components (source:manufacturer:vehicle_model:market), got {len(parts)}"
        )
    source, manufacturer, vehicle_model, market = parts
    return CollectionContext(
        source=source, manufacturer=manufacturer, vehicle_model=vehicle_model, market=market
    )


def require_spec_identity_matches_context(
    identity: SpecIdentity, context: CollectionContext
) -> None:
    """004 (Blocker 1, correção do achado do Codex): valida que uma
    `SpecIdentity` (recuperada por `spec_key`/`stable_key()`) pertence ao
    MESMO contexto operacional (`source`/`manufacturer`/`vehicle_model`/
    `market`) de `context` — nunca confia apenas em quem chamou
    `process_capture()`/`try_finalize_spec_entry()` com um `spec_key`.

    `stable_key()` é um hash — não há como "interpretá-lo" de volta em
    componentes sem consultar o registro (`spec_registry`), já que 2 dos 6
    campos da identidade (`model_code`/`amayama_catalog_id`) são dados
    descobertos, não parte do `CollectionContext`. Por isso esta função pura
    recebe a `SpecIdentity` já resolvida (a resolução por `spec_key` — I/O —
    é responsabilidade da camada de orquestração, nunca do domínio) e
    reaproveita a própria construção/normalização de `CollectionContext`
    para comparar — nenhuma regra de comparação nova é inventada aqui.
    """
    identity_context = CollectionContext(
        source=identity.source,
        manufacturer=identity.manufacturer,
        vehicle_model=identity.vehicle_model,
        market=identity.market,
    )
    if identity_context.scope() != context.scope():
        raise ContextScopeMismatchError(
            f"spec identity scope {identity_context.scope()!r} does not match "
            f"context {context.scope()!r} — refusing to process/persist this "
            "spec_key under a mismatched operational context"
        )
