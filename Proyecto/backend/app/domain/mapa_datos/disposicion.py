"""
HU-34 criterio 3 · Disposición del mapa (dónde va cada nodo y por dónde pasa cada flujo) para el
diagrama del informe PDF.

Disposición por capas (Sugiyama), de izquierda a derecha, en el sentido en que viajan los datos:
  1. Se quitan los ciclos (los flujos de vuelta no cuentan para asignar columnas).
  2. Columna = el camino más largo desde un origen (quien solo envía queda a la izquierda).
     Los terceros que solo reciben van a la última columna; los elementos sin flujos se
     ubican por tipo (sistemas, bases de datos, terceros).
  3. Un flujo que salta columnas recibe un punto de paso (nodo virtual) en cada columna
     intermedia: así la flecha pasa ENTRE los nodos y no por detrás de ellos.
  4. Dentro de cada columna se ordena por baricentro (promedio de la posición de sus vecinos,
     contando los puntos de paso) para que se crucen menos flechas.

Es el mismo algoritmo que dibuja el mapa navegable del panel (frontend-next/lib/mapaDatos.ts):
la pantalla, el PNG y el PDF muestran el mapa con la misma forma.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

ANCHO_NODO = 200
ALTO_NODO = 74
ALTO_PASO = 10           # alto que ocupa un punto de paso de un flujo en su columna
SEPARACION_X = 120
SEPARACION_Y = 28
SEPARACION_PASO = 12     # separación si uno de los dos vecinos es un punto de paso
MARGEN = 24
_ORDEN_TIPO = {"sistema": 0, "base_datos": 1, "tercero": 2}


@dataclass(frozen=True)
class NodoDisposicion:
    id: int
    columna: int
    fila: int
    x: float
    y: float


@dataclass(frozen=True)
class Disposicion:
    nodos: dict[int, NodoDisposicion]
    ancho: float
    alto: float
    columnas: int
    # id del flujo -> puntos de paso [(x de la columna, y central)] en las columnas intermedias
    pasos: dict[int, list[tuple[float, float]]] = field(default_factory=dict)


def calcular(elementos: list[tuple[int, str, str]], flujos: list[tuple[int, int, int]]) -> Disposicion:
    """`elementos`: (id, tipo, nombre). `flujos`: (id, origen_id, destino_id)."""
    orden = sorted(elementos, key=lambda e: (_ORDEN_TIPO.get(e[1], 9), e[2].lower(), e[0]))
    ids = [e[0] for e in orden]
    tipo = {e[0]: e[1] for e in orden}
    existe = set(ids)
    validos = [(fid, o, d) for fid, o, d in sorted(flujos) if o in existe and d in existe and o != d]
    sucesores: dict[int, list[int]] = defaultdict(list)
    for _, o, d in validos:
        if d not in sucesores[o]:
            sucesores[o].append(d)

    # 1. aristas del DAG (sin las que cierran un ciclo), con DFS iterativo en orden determinista
    estado: dict[int, int] = {}          # 1 = en la pila, 2 = terminado
    dag: dict[int, list[int]] = defaultdict(list)
    for raiz in ids:
        if raiz in estado:
            continue
        pila = [(raiz, iter(sucesores[raiz]))]
        estado[raiz] = 1
        while pila:
            v, it = pila[-1]
            siguiente = next(it, None)
            if siguiente is None:
                estado[v] = 2
                pila.pop()
                continue
            if estado.get(siguiente) == 1:
                continue                  # flujo de vuelta: no cuenta para ordenar
            dag[v].append(siguiente)
            if siguiente not in estado:
                estado[siguiente] = 1
                pila.append((siguiente, iter(sucesores[siguiente])))

    # 2. columna = camino más largo (Kahn)
    entrada = {v: 0 for v in ids}
    for v in ids:
        for w in dag[v]:
            entrada[w] += 1
    columna = {v: 0 for v in ids}
    cola = deque(v for v in ids if entrada[v] == 0)
    while cola:
        v = cola.popleft()
        for w in dag[v]:
            columna[w] = max(columna[w], columna[v] + 1)
            entrada[w] -= 1
            if entrada[w] == 0:
                cola.append(w)

    conectados = {v for v in ids if sucesores[v]} | {w for v in ids for w in sucesores[v]}
    maxima = max((columna[v] for v in conectados), default=0)
    if not conectados:
        maxima = max((_ORDEN_TIPO.get(tipo[v], 0) for v in ids), default=0)
    for v in ids:
        if v not in conectados:
            columna[v] = min(_ORDEN_TIPO.get(tipo[v], 0), maxima) if tipo[v] != "tercero" else maxima
        elif tipo[v] == "tercero" and not dag[v]:
            columna[v] = maxima           # terceros que solo reciben: al final

    # 3. puntos de paso de los flujos que saltan columnas
    col: dict[str, int] = {f"e{v}": columna[v] for v in ids}
    suc: dict[str, list[str]] = defaultdict(list)
    pred: dict[str, list[str]] = defaultdict(list)
    virtuales_de: dict[int, list[str]] = {}
    for fid, o, d in validos:
        co, cd = columna[o], columna[d]
        cadena = [f"e{o}"]
        if cd - co > 1:
            intermedios = [f"v{fid}-{c}" for c in range(co + 1, cd)]
            for c, k in zip(range(co + 1, cd), intermedios):
                col[k] = c
            virtuales_de[fid] = intermedios
            cadena += intermedios
        cadena.append(f"e{d}")
        for a, b in zip(cadena, cadena[1:]):
            suc[a].append(b)
            pred[b].append(a)

    # 4. orden dentro de cada columna por baricentro (4 barridos)
    total_columnas = (max(columna.values()) + 1) if ids else 0
    capas: list[list[str]] = [[] for _ in range(total_columnas)]
    for v in ids:
        capas[columna[v]].append(f"e{v}")
    for fid in sorted(virtuales_de):
        for k in virtuales_de[fid]:
            capas[col[k]].append(k)

    def posicion() -> dict[str, float]:
        return {k: float(i) for capa in capas for i, k in enumerate(capa)}

    for barrido in range(4):
        hacia_derecha = barrido % 2 == 0
        rango = range(1, total_columnas) if hacia_derecha else range(total_columnas - 2, -1, -1)
        for c in rango:
            pos = posicion()
            vecinos = pred if hacia_derecha else suc

            def bari(k: str, i: int, pos=pos, vecinos=vecinos, c=c) -> tuple[float, int]:
                ref = [pos[w] for w in vecinos[k] if w in pos and col[w] != c]
                return (sum(ref) / len(ref) if ref else float(i), i)

            capas[c] = [k for _, k in sorted(((bari(k, i), k) for i, k in enumerate(capas[c])), key=lambda x: x[0])]

    # 5. coordenadas (alturas variables: nodos y puntos de paso)
    def alto_item(k: str) -> float:
        return ALTO_NODO if k.startswith("e") else ALTO_PASO

    def separacion(a: str, b: str) -> float:
        return SEPARACION_Y if a.startswith("e") and b.startswith("e") else SEPARACION_PASO

    def alto_capa(capa: list[str]) -> float:
        return sum(alto_item(k) for k in capa) + sum(separacion(a, b) for a, b in zip(capa, capa[1:]))

    alto_max = max((alto_capa(capa) for capa in capas), default=0)
    alto_total = MARGEN * 2 + alto_max
    nodos: dict[int, NodoDisposicion] = {}
    centro_paso: dict[str, tuple[float, float]] = {}
    for c, capa in enumerate(capas):
        x = MARGEN + c * (ANCHO_NODO + SEPARACION_X)
        y = MARGEN + (alto_max - alto_capa(capa)) / 2
        fila = 0
        for i, k in enumerate(capa):
            if i:
                y += separacion(capa[i - 1], k)
            if k.startswith("e"):
                v = int(k[1:])
                nodos[v] = NodoDisposicion(v, c, fila, x, y)
                fila += 1
            else:
                centro_paso[k] = (x, y + ALTO_PASO / 2)
            y += alto_item(k)
    pasos = {fid: [centro_paso[k] for k in ks] for fid, ks in virtuales_de.items()}
    ancho = MARGEN * 2 + max(0, total_columnas * (ANCHO_NODO + SEPARACION_X) - SEPARACION_X)
    return Disposicion(nodos, ancho, alto_total, total_columnas, pasos)
