import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as EventoMouse,
  type ReactNode,
  type TouchEvent as EventoToque,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  CheckBadgeIcon,
  CheckCircleIcon as CheckCircleMini,
  ChevronLeftIcon,
  XMarkIcon as XMarkMini,
} from "@heroicons/react/20/solid";
import { ArrowUturnLeftIcon, PhotoIcon, TrashIcon, XMarkIcon } from "@heroicons/react/24/outline";
import {
  CheckBadgeIcon as AprobarTodasGrande,
  CheckCircleIcon,
  CheckIcon,
} from "@heroicons/react/24/solid";

import { ErrorApi, admin, haySesion } from "../api/client";
import type { EstadoFoto, EventoAdmin, FotoAdmin } from "../api/tipos";
import Boton from "../comp/Boton";
import BotonChico from "../comp/BotonChico";
import Cargando from "../comp/Cargando";
import ChipEstado from "../comp/ChipEstado";
import Confirmar from "../comp/Confirmar";
import Foto from "../comp/Foto";
import type { Icono } from "../comp/icono";
import MensajeError from "../comp/MensajeError";
import { sinArchivos } from "../lib/descargas";
import { fechaCorta, fechaLarga } from "../lib/fecha";
import { useVolverALista } from "./navegacion";
import { comun } from "./textos/comun";
import { textosRevisar as t } from "./textos/revisar";
import { useAtajos, type Accion } from "./useAtajos";
import { useAlPerderSesion } from "./useSesion";

const REFRESCO_MS = 10_000;
const LIMITE = 200;
/** Cuánto hay que deslizar el dedo sobre la foto para pasar a la otra. */
const DESLIZAR_PX = 50;

interface Ubicada {
  foto: FotoAdmin;
  indice: number;
}

/**
 * Una decisión: una foto sola, o varias juntas (la selección, Aprobar todas).
 * Deshacer devuelve la decisión entera: después de "Aprobar todas (40)", un
 * toque en Deshacer trae las cuarenta, no una sola.
 */
interface Decision {
  fotos: Ubicada[];
  estado: EstadoFoto;
  /** Ya la devolvió Deshacer: si su pedido falla después, las fotos ya están
   *  en la lista y no hay nada que avisar. */
  deshecha: boolean;
  /** Su pedido falló: la base nunca cambió, y Deshacer no tiene nada que mandar. */
  fallo: boolean;
}

/**
 * Los pedidos de una misma foto salen de a uno, en el orden en que se
 * decidieron: cada uno espera a que termine el anterior, salga bien o mal.
 *
 * Sin esto, `A` y enseguida `Z` mandaban "aprobada" y "pendiente" en paralelo.
 * El backend lee la foto antes de escribirla: si el "pendiente" leía antes de
 * que se guardara el "aprobada", no cambiaba nada, y después ganaba la
 * aprobación. La foto quedaba proyectándose mientras la bandeja la mostraba
 * pendiente.
 *
 * `enCamino` guarda, por foto, el último pedido que salió. Un lote espera a los
 * de todas sus fotos.
 */
function enOrden<T>(
  enCamino: Map<number, Promise<unknown>>,
  ids: number[],
  pedir: () => Promise<T>,
): Promise<T> {
  const anteriores = ids.flatMap((id) => {
    const anterior = enCamino.get(id);
    return anterior ? [anterior] : [];
  });
  const pedido = Promise.all(anteriores).then(pedir);
  // Lo que espera el siguiente: que éste termine, bien o mal.
  const terminado = pedido.then(
    () => undefined,
    () => undefined,
  );
  for (const id of ids) enCamino.set(id, terminado);
  void terminado.then(() => {
    for (const id of ids) if (enCamino.get(id) === terminado) enCamino.delete(id);
  });
  return pedido;
}

/** Devuelve cada foto a la posición que tenía. Van en orden de posición para
 *  que varias seguidas vuelvan en el mismo orden. Nunca inserta dos veces la
 *  misma foto, pase lo que pase. */
function reinsertar(lista: FotoAdmin[], ubicadas: Ubicada[]): FotoAdmin[] {
  const copia = [...lista];
  for (const { foto, indice } of [...ubicadas].sort((a, b) => a.indice - b.indice)) {
    if (copia.some((f) => f.id === foto.id)) continue;
    copia.splice(Math.min(indice, copia.length), 0, foto);
  }
  return copia;
}

/**
 * Los botones grandes de la barra de abajo, más angostos en el celular. Con
 * el ícono al lado, "Rechazar", "Deshacer" y "Aprobar" no entran en una fila
 * de 375 px (medido: piden ~120 px cada uno y la columna da ~108): en el
 * celular el ícono va ARRIBA del texto, como en las barras de herramientas de
 * iOS, y cada botón mide lo que su palabra (~90 px). Así entran hasta en 320.
 * Desde `sm` el ícono vuelve al lado y el botón, a su tamaño normal.
 *
 * `[&>svg]:ml-0` saca el -ml-1 que Boton le pone al ícono para pegarlo al
 * texto: apilado, lo correría del centro. El `!` gana sobre las clases de
 * Boton sin depender del orden en que Tailwind escribe el CSS.
 */
const COMPACTO =
  "whitespace-nowrap !text-base max-sm:flex-col max-sm:!gap-0.5 max-sm:!px-2 max-sm:[&>svg]:ml-0 " +
  "sm:!text-lg";

/** Mismo vidrio oscuro que la barra del resto del panel (LayoutAdmin). */
const BARRA = "border-borde bg-black/60 backdrop-blur-2xl backdrop-saturate-150";

/**
 * La bandeja. Objetivo medible: cincuenta fotos en menos de dos minutos.
 *
 * Sin confirmaciones. Nada de "¿estás segura?" antes de rechazar: duplicaría los
 * clics de la tarea que más se repite para prevenir un error que se deshace con
 * una tecla. La red de seguridad es Deshacer (Z). La única pregunta es Aprobar
 * todas, que manda decenas de fotos a la pantalla de un toque.
 *
 * Pantalla completa, sin la barra del panel: la foto necesita todo el alto.
 */
export default function PaginaRevisar() {
  const { id = "" } = useParams();
  const idEvento = Number(id);
  const navegar = useNavigate();

  const [evento, setEvento] = useState<EventoAdmin | null>(null);
  const [fotos, setFotos] = useState<FotoAdmin[]>([]);
  const [indice, setIndice] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [intento, setIntento] = useState(0);
  const [aviso, setAviso] = useState<string | null>(null);

  // Las que llegaron mientras se revisa. NO se incorporan solas: una lista que
  // se reacomoda sola hace que se apruebe la foto equivocada.
  const [enEspera, setEnEspera] = useState<FotoAdmin[]>([]);

  // Selección de varias. En el celular no hay Shift: el botón Seleccionar
  // activa un modo donde tocar una miniatura la marca o la desmarca. En la
  // compu, Shift+clic sigue marcando un rango y entra al mismo modo.
  const [seleccionando, setSeleccionando] = useState(false);
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const anclaSeleccion = useRef<number | null>(null);

  const [confirmarTodas, setConfirmarTodas] = useState(false);

  // El historial vive en una ref (ver el OJO de `moderar`). `decisiones` es su
  // largo, en estado, sólo para que Deshacer sepa si mostrarse habilitado.
  const historial = useRef<Decision[]>([]);
  const [decisiones, setDecisiones] = useState(0);
  const ultimoId = useRef(0);
  // Todas las fotos que ya pasaron por la bandeja. Una misma foto no puede
  // entrar dos veces a la lista: se aprobaría dos veces y React se confunde
  // con dos claves iguales.
  const conocidas = useRef<Set<number>>(new Set());

  // El último pedido de moderación de cada foto (ver `enOrden`).
  const enCamino = useRef(new Map<number, Promise<unknown>>());

  const tira = useRef<HTMLDivElement>(null);
  const toque = useRef<{ x: number; y: number } | null>(null);

  // La posición siempre válida, aunque el estado haya quedado afuera de la
  // lista (deshacer, una foto que volvió por un error, la lista vacía). Todo
  // lo que decide sobre "la foto actual" usa esta y no `indice` crudo.
  const posicion = fotos.length === 0 ? 0 : Math.min(Math.max(0, indice), fotos.length - 1);
  const actual = fotos[posicion] ?? null;

  // La lista y la posición al día también ENTRE dos dibujos. Un pedido que
  // falla y vuelve a poner su foto en la lista puede llegar en cualquier
  // momento, y puede llegar más de uno junto (se cortó el wifi con varios en
  // camino): cada uno tiene que partir de lo que dejó el anterior, no de lo
  // último que se dibujó. Todo cambio de la lista o de la posición pasa por
  // `fijarFotos` y `fijarIndice`, que actualizan esto y el estado a la vez.
  const fotosVivas = useRef<FotoAdmin[]>(fotos);
  const posicionViva = useRef(posicion);
  fotosVivas.current = fotos;
  posicionViva.current = posicion;

  const fijarFotos = useCallback((nueva: FotoAdmin[]) => {
    fotosVivas.current = nueva;
    setFotos(nueva);
  }, []);

  const fijarIndice = useCallback((nuevo: number) => {
    posicionViva.current = nuevo;
    setIndice(nuevo);
  }, []);

  /**
   * Devuelve fotos a su lugar SIN cambiar la que se está mirando. Si la foto
   * de la pantalla cambiara bajo el dedo, la próxima A aprobaría la que se
   * acababa de rechazar, justo lo que la bandeja existe para evitar. La que
   * vuelve queda a la vista en la fila de miniaturas, con el aviso de arriba.
   */
  const devolver = useCallback(
    (ubicadas: Ubicada[]) => {
      const antes = fotosVivas.current;
      const mirando = antes[posicionViva.current]?.id;
      const nueva = reinsertar(antes, ubicadas);
      fijarFotos(nueva);
      if (mirando === undefined) return;
      const donde = nueva.findIndex((f) => f.id === mirando);
      if (donde >= 0) fijarIndice(donde);
    },
    [fijarFotos, fijarIndice],
  );
  const pendientes = fotos.length + enEspera.length;

  /** Un 401 en cualquier pedido (la sesión venció o la cuenta se dio de baja)
   *  manda al login. Un 403 no: NO_AUTORIZADO viaja con los dos. */
  const siSeVencio = useAlPerderSesion();

  // "‹ Volver" lleva a la lista de donde se vino (el historial con su
  // filtro) o, si no, a la lista donde vive el evento.
  const lista = useVolverALista(evento);

  // ── Carga inicial ───────────────────────────────────────────
  useEffect(() => {
    if (!haySesion()) {
      navegar("/admin/login", { replace: true });
      return;
    }
    let vivo = true;
    setError(null);
    setCargando(true);
    (async () => {
      try {
        // Un admin ve todos los eventos; un organizador, sólo los suyos. Si
        // éste no está en la lista, para esta cuenta no existe.
        const eventos = await admin.eventos();
        const mio = eventos.find((e) => e.id === idEvento);
        if (!mio) throw new ErrorApi("EVENTO_NO_ENCONTRADO", t.noEncontrado, 404);
        if (sinArchivos(mio)) {
          // A los 30 días las imágenes se borran de Cloudinary. Las filas
          // siguen en la base (nada se borra), pero pedirlas sólo dibujaría
          // miniaturas rotas: no se piden. Desde el día del borrado, aunque
          // la limpieza todavía no haya pasado: puede borrar mientras se mira.
          if (!vivo) return;
          setEvento(mio);
          fijarFotos([]);
          conocidas.current = new Set();
          ultimoId.current = 0;
          setCargando(false);
          return;
        }
        const lista = await admin.fotos(idEvento, { estado: "pendiente", limite: LIMITE });
        if (!vivo) return;
        setEvento(mio);
        fijarFotos(lista.fotos);
        conocidas.current = new Set(lista.fotos.map((f) => f.id));
        ultimoId.current = lista.ultimo_id;
        setCargando(false);
      } catch (e) {
        if (!vivo || siSeVencio(e)) return;
        setError(e);
        setCargando(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, [idEvento, navegar, siSeVencio, intento, fijarFotos]);

  // El nombre del evento en el título de la pestaña: con dos pestañas abiertas
  // es lo único que las distingue en la barra.
  useEffect(() => {
    if (evento) document.title = comun.tituloPestana(t.pestana(evento.nombre, pendientes));
  }, [evento, pendientes]);

  // ── Auto-refresco que no mueve la posición ──────────────────
  useEffect(() => {
    // Con las fotos borradas no llega nada nuevo: el evento quedó cerrado.
    if (!evento || sinArchivos(evento)) return;
    // Un pedido por vez. Con Render dormido o el wifi del salón, uno puede
    // tardar más de diez segundos: el siguiente saldría con el mismo `desde` y
    // las mismas fotos entrarían dos veces.
    let pidiendo = false;
    const id = window.setInterval(async () => {
      if (pidiendo) return;
      pidiendo = true;
      try {
        const lista = await admin.fotos(idEvento, {
          estado: "pendiente",
          desde: ultimoId.current,
          limite: LIMITE,
        });
        ultimoId.current = Math.max(ultimoId.current, lista.ultimo_id);
        const nuevas = lista.fotos.filter((f) => !conocidas.current.has(f.id));
        if (nuevas.length === 0) return;
        nuevas.forEach((f) => conocidas.current.add(f.id));
        setEnEspera((previas) => [...previas, ...nuevas]);
      } catch (e) {
        // Que falle el refresco no puede interrumpir la tanda. Salvo que la
        // sesión se haya vencido: ahí ya nada de lo que se toque va a guardarse.
        siSeVencio(e);
      } finally {
        pidiendo = false;
      }
    }, REFRESCO_MS);
    return () => window.clearInterval(id);
  }, [evento, idEvento, siSeVencio]);

  const incorporar = useCallback(() => {
    fijarFotos([...fotosVivas.current, ...enEspera]);
    setEnEspera([]);
  }, [enEspera, fijarFotos]);

  // Al terminar la tanda se incorporan solas: ahí ya no hay posición que mover.
  useEffect(() => {
    if (fotos.length === 0 && enEspera.length > 0) incorporar();
  }, [fotos.length, enEspera.length, incorporar]);

  // La miniatura de la foto actual siempre a la vista, también cuando se
  // avanza con el teclado o deslizando. Se mueve sólo la fila, nunca la página:
  // scrollIntoView desplazaría todo si la fila quedó fuera de pantalla.
  useEffect(() => {
    const fila = tira.current;
    const boton = fila?.children[posicion] as HTMLElement | undefined;
    if (!fila || !boton) return;
    const izquierda = boton.offsetLeft;
    const derecha = izquierda + boton.offsetWidth;
    if (izquierda < fila.scrollLeft || derecha > fila.scrollLeft + fila.clientWidth) {
      fila.scrollTo({ left: izquierda - (fila.clientWidth - boton.offsetWidth) / 2, behavior: "smooth" });
    }
  }, [posicion, fotos.length]);

  // La que sigue ya descargada: al aprobar, la próxima aparece al instante.
  useEffect(() => {
    const siguiente = fotos[posicion + 1];
    if (!siguiente) return;
    const imagen = new Image();
    imagen.src = siguiente.url;
  }, [fotos, posicion]);

  // ── Historial para Deshacer ─────────────────────────────────
  const anotar = useCallback((decision: Decision) => {
    historial.current.push(decision);
    setDecisiones(historial.current.length);
  }, []);

  /** Si el pedido falló, la decisión nunca existió: que Deshacer no la cuente. */
  const olvidar = useCallback((decision: Decision) => {
    historial.current = historial.current.filter((d) => d !== decision);
    setDecisiones(historial.current.length);
  }, []);

  const salirDeSeleccion = useCallback(() => {
    setSeleccionando(false);
    setSeleccion(new Set());
  }, []);

  // ── Decisión optimista ──────────────────────────────────────
  // OJO: nada de efectos secundarios adentro de un updater de estado. React
  // puede invocar el updater más de una vez —en StrictMode lo hace siempre— y
  // el historial terminaba con dos entradas por foto. Se notaba recién al
  // deshacer: Z seguía "deshaciendo" después de agotar el historial e insertaba
  // fotos duplicadas. Por eso todo el trabajo se hace acá afuera.
  const moderar = useCallback(
    (estado: EstadoFoto) => {
      const lista = fotosVivas.current;
      const lugar = posicionViva.current;
      const foto = lista[lugar];
      if (!foto) return;

      const decision: Decision = {
        fotos: [{ foto, indice: lugar }],
        estado,
        deshecha: false,
        fallo: false,
      };
      anotar(decision);
      const restantes = lista.filter((_, i) => i !== lugar);
      fijarFotos(restantes);
      fijarIndice(Math.min(lugar, Math.max(0, restantes.length - 1)));

      // El pedido viaja en segundo plano. Esperar la respuesta entre foto y
      // foto convierte dos minutos en diez.
      enOrden(enCamino.current, [foto.id], () => admin.moderar(foto.id, estado)).catch((e: unknown) => {
        decision.fallo = true;
        olvidar(decision);
        const vencida = siSeVencio(e);
        if (decision.deshecha) return;
        devolver(decision.fotos);
        if (!vencida) setAviso(t.avisos.fallo);
      });
    },
    [anotar, olvidar, siSeVencio, fijarFotos, fijarIndice, devolver],
  );

  /** Varias juntas, en un solo pedido: en una fiesta llegan ráfagas de veinte
   *  fotos casi todas buenas. */
  const moderarVarias = useCallback(
    (elegidas: ReadonlySet<number>, estado: EstadoFoto) => {
      const lista = fotosVivas.current;
      const guardadas: Ubicada[] = [];
      lista.forEach((foto, i) => {
        if (elegidas.has(foto.id)) guardadas.push({ foto, indice: i });
      });
      const primera = guardadas[0];
      if (!primera) return;

      const decision: Decision = { fotos: guardadas, estado, deshecha: false, fallo: false };
      anotar(decision);
      const restantes = lista.filter((f) => !elegidas.has(f.id));
      fijarFotos(restantes);
      // Se sigue desde donde estaba la primera, no desde el principio.
      fijarIndice(Math.min(primera.indice, Math.max(0, restantes.length - 1)));
      salirDeSeleccion();
      anclaSeleccion.current = null;

      const ids = guardadas.map((g) => g.foto.id);
      enOrden(enCamino.current, ids, () => admin.moderarLote(ids, estado)).catch((e: unknown) => {
        decision.fallo = true;
        olvidar(decision);
        const vencida = siSeVencio(e);
        if (decision.deshecha) return;
        devolver(guardadas);
        if (!vencida) setAviso(t.avisos.falloVarias);
      });
    },
    [anotar, olvidar, salirDeSeleccion, siSeVencio, fijarFotos, fijarIndice, devolver],
  );

  const deshacer = useCallback(() => {
    const ultima = historial.current.pop();
    if (!ultima) return;
    ultima.deshecha = true;
    setDecisiones(historial.current.length);
    const nueva = reinsertar(fotosVivas.current, ultima.fotos);
    fijarFotos(nueva);
    // Deshacer SÍ mueve la vista, a propósito: a la foto que vuelve, que es la
    // que se quería volver a mirar.
    const primera = [...ultima.fotos].sort((a, b) => a.indice - b.indice)[0];
    const donde = primera ? nueva.findIndex((f) => f.id === primera.foto.id) : -1;
    fijarIndice(Math.max(0, donde));

    // Sale después del pedido de la decisión (ver `enOrden`). Si ése falló, la
    // base nunca cambió y no hay nada que deshacer allá.
    const ids = ultima.fotos.map((u) => u.foto.id);
    const [unica] = ids;
    enOrden(enCamino.current, ids, (): Promise<unknown> => {
      if (ultima.fallo) return Promise.resolve(null);
      return ids.length === 1 && unica !== undefined
        ? admin.moderar(unica, "pendiente")
        : admin.moderarLote(ids, "pendiente");
    }).catch((e: unknown) => {
      if (!siSeVencio(e)) setAviso(t.avisos.falloDeshacer);
    });
  }, [siSeVencio, fijarFotos, fijarIndice]);

  const alActuar = useCallback(
    (accion: Accion) => {
      switch (accion) {
        // Con la posición viva y no con `posicion`: dos flechas seguidas antes
        // de que React vuelva a dibujar tienen que mover dos lugares. El
        // Math.min lo trae de vuelta si había quedado afuera de la lista.
        case "anterior": {
          const largo = fotosVivas.current.length;
          fijarIndice(Math.max(0, Math.min(posicionViva.current, largo - 1) - 1));
          break;
        }
        case "siguiente": {
          const largo = fotosVivas.current.length;
          fijarIndice(Math.min(Math.max(0, largo - 1), Math.max(0, posicionViva.current) + 1));
          break;
        }
        case "aprobar":
        case "rechazar": {
          const estado: EstadoFoto = accion === "aprobar" ? "aprobada" : "rechazada";
          if (seleccion.size > 0) moderarVarias(seleccion, estado);
          // En modo selección sin nada marcado, A y R no hacen nada: la foto
          // de arriba no es la que se eligió.
          else if (!seleccionando) moderar(estado);
          break;
        }
        case "deshacer":
          deshacer();
          break;
        case "cancelar":
          salirDeSeleccion();
          break;
      }
    },
    [seleccion, seleccionando, moderar, moderarVarias, deshacer, salirDeSeleccion, fijarIndice],
  );

  const borradas = evento !== null && sinArchivos(evento);

  useAtajos(alActuar, !cargando && !error && !confirmarTodas && !borradas);

  function alternar(idFoto: number) {
    setSeleccion((previa) => {
      const nueva = new Set(previa);
      if (nueva.has(idFoto)) nueva.delete(idFoto);
      else nueva.add(idFoto);
      return nueva;
    });
  }

  function alTocarMiniatura(i: number, evento: EventoMouse) {
    const foto = fotos[i];
    if (!foto) return;

    if (evento.shiftKey && anclaSeleccion.current !== null) {
      const desde = Math.min(anclaSeleccion.current, i);
      const hasta = Math.max(anclaSeleccion.current, i);
      const nueva = new Set(seleccion);
      for (let k = desde; k <= hasta; k++) {
        const f = fotos[k];
        if (f) nueva.add(f.id);
      }
      setSeleccion(nueva);
      setSeleccionando(true);
      return;
    }

    anclaSeleccion.current = i;
    // Tocar una miniatura siempre la muestra en grande, también al marcarla:
    // se decide mirando la foto, no la miniatura.
    fijarIndice(i);
    if (seleccionando || evento.metaKey || evento.ctrlKey) {
      alternar(foto.id);
      setSeleccionando(true);
    }
  }

  function aprobarTodas() {
    setConfirmarTodas(false);
    moderarVarias(new Set(fotosVivas.current.map((f) => f.id)), "aprobada");
  }

  // ── Deslizar sobre la foto grande, en el celular ────────────
  function alEmpezarToque(evento: EventoToque) {
    const dedo = evento.touches[0];
    toque.current = dedo && evento.touches.length === 1 ? { x: dedo.clientX, y: dedo.clientY } : null;
  }

  function alTerminarToque(evento: EventoToque) {
    const inicio = toque.current;
    toque.current = null;
    const dedo = evento.changedTouches[0];
    if (!inicio || !dedo || evento.touches.length > 0) return;
    const dx = dedo.clientX - inicio.x;
    const dy = dedo.clientY - inicio.y;
    // Sólo un gesto claramente horizontal: el vertical es para desplazar la
    // página cuando la bandeja no entra en la pantalla.
    if (Math.abs(dx) < DESLIZAR_PX || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    alActuar(dx < 0 ? "siguiente" : "anterior");
  }

  // ── Estados de carga y error ────────────────────────────────
  if (error) {
    const deRed = error instanceof ErrorApi && error.esDeRed;
    return (
      <main className="flex h-full flex-col items-center justify-center gap-2 p-4">
        <MensajeError error={error} onReintentar={deRed ? () => setIntento((n) => n + 1) : undefined} />
        <div className="w-full max-w-xs">
          <Boton variante={deRed ? "secundario" : "principal"} onClick={() => navegar(lista.a)}>
            {t.volverA(lista.texto)}
          </Boton>
        </div>
      </main>
    );
  }

  if (cargando || !evento) {
    return (
      <main className="flex h-full items-center justify-center">
        <Cargando texto={t.cargando} />
      </main>
    );
  }

  const marcadas = seleccion.size;

  return (
    // Con poca altura (un celular acostado) la foto no puede quedar en cero:
    // tiene un mínimo y, si no entra todo, la página scrollea. Arriba y abajo
    // quedan fijos el encabezado y los botones.
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Barra de contexto fija: con dos pestañas abiertas, el nombre grande
          es lo que evita aprobar las fotos del evento equivocado. */}
      <header className={`sticky top-0 z-30 shrink-0 border-b pt-[env(safe-area-inset-top)] ${BARRA}`}>
        <div className="flex min-h-16 items-center gap-2 px-2 py-2 sm:gap-4 sm:px-4">
          <Link
            to={lista.a}
            aria-label={t.volverA(lista.texto)}
            className={
              "inline-flex min-h-11 shrink-0 items-center gap-0.5 rounded-full pl-1 pr-2 text-base text-acento " +
              "hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
            }
          >
            <ChevronLeftIcon aria-hidden className="h-6 w-6 shrink-0" />
            {t.volver}
          </Link>

          <div className="min-w-0 flex-1">
            <h1 className="line-clamp-2 break-words text-lg font-semibold leading-tight sm:text-2xl">
              {evento.nombre}
            </h1>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-tenue">
              <span className="whitespace-nowrap">{fechaCorta(evento.fecha_evento)}</span>
              <ChipEstado estado={evento.estado} />
            </p>
          </div>

          {/* Siempre visible, arriba y grande: es la única métrica que importa
              en vivo. Cuenta también las nuevas que todavía no se sumaron.
              Con las fotos borradas no hay nada que contar: un "0" diría que
              se revisó todo, y puede que no. */}
          {!borradas && (
            <p className="shrink-0 pl-1 text-right leading-none">
              <strong className="block text-3xl font-semibold tabular-nums sm:text-4xl">{pendientes}</strong>
              <span className="text-xs text-tenue sm:text-sm">{t.pendientes(pendientes)}</span>
            </p>
          )}
        </div>
      </header>

      {aviso && (
        <div role="alert" className="flex shrink-0 items-center justify-between gap-3 border-b border-borde bg-rojo/15 px-4 py-1">
          <p className="min-w-0 text-sm text-rojo sm:text-base">{aviso}</p>
          <BotonChico className="shrink-0" icono={XMarkMini} onClick={() => setAviso(null)}>
            {comun.cerrar}
          </BotonChico>
        </div>
      )}

      {borradas ? (
        <Vacio
          icono={TrashIcon}
          titulo={evento.fotos_borradas_en ? t.borradas.titulo : t.borrando.titulo}
          texto={evento.fotos_borradas_en ? t.borradas.texto(fechaLarga(evento.fotos_borradas_en)) : t.borrando.texto}
        >
          <Boton onClick={() => navegar(lista.a)}>{t.volverA(lista.texto)}</Boton>
        </Vacio>
      ) : actual ? (
        <>
          {/* Foto grande: se decide mirando la foto en grande, no la miniatura. */}
          <section
            className="relative min-h-[45vh] flex-1"
            onTouchStart={alEmpezarToque}
            onTouchEnd={alTerminarToque}
          >
            <div className="absolute inset-0">
              <Foto
                key={actual.id}
                url={actual.url}
                ancho={actual.ancho}
                alto={actual.alto}
                alt={t.foto(actual.nombre_invitado)}
              />
            </div>

            {/* Flota encima de la foto en vez de empujarla: que aparezca el
                aviso no puede mover nada de lugar mientras se está por tocar. */}
            {enEspera.length > 0 && (
              <BotonChico
                variante="azul"
                onClick={incorporar}
                className="absolute left-1/2 top-3 z-10 max-w-[calc(100%-7rem)] -translate-x-1/2 shadow-lg shadow-black/40"
              >
                {t.nuevas(enEspera.length)}
              </BotonChico>
            )}

            {seleccionando && (
              <button
                type="button"
                onClick={() => alternar(actual.id)}
                aria-pressed={seleccion.has(actual.id)}
                aria-label={t.marcar}
                className="absolute right-2 top-2 z-10 flex h-11 w-11 items-center justify-center rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-acento"
              >
                <Tilde marcada={seleccion.has(actual.id)} grande />
              </button>
            )}

            {actual.nombre_invitado && (
              <p className="vidrio-oscuro pointer-events-none absolute bottom-3 left-1/2 max-w-[90%] -translate-x-1/2 truncate rounded-full px-4 py-1 text-base sm:text-lg">
                {actual.nombre_invitado}
              </p>
            )}
          </section>

          <div className="shrink-0 border-t border-borde">
            {/* flex-wrap: con un número de tres cifras y la letra agrandada,
                "Seleccionar" y "Aprobar todas (200)" pasan a dos renglones
                antes que empujar la página hacia el costado. */}
            {(seleccionando || fotos.length > 1) && (
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 pt-2">
                {seleccionando ? (
                  <>
                    <p className="min-w-0 text-sm font-medium sm:text-base" aria-live="polite">
                      {marcadas > 0 ? t.seleccionadas(marcadas) : t.tocaParaMarcar}
                    </p>
                    <BotonChico className="shrink-0" icono={XMarkMini} onClick={salirDeSeleccion}>
                      {comun.cancelar}
                    </BotonChico>
                  </>
                ) : (
                  <>
                    <BotonChico icono={CheckCircleMini} onClick={() => setSeleccionando(true)}>
                      {t.seleccionar}
                    </BotonChico>
                    <BotonChico icono={CheckBadgeIcon} onClick={() => setConfirmarTodas(true)}>
                      {t.aprobarTodas(fotos.length)}
                    </BotonChico>
                  </>
                )}
              </div>
            )}

            {/* Fila de miniaturas. `relative` para que offsetLeft de cada una
                se mida desde la fila (lo usa el efecto que la sigue). */}
            <div
              ref={tira}
              role="group"
              aria-label={t.fila}
              className="relative flex select-none gap-2 overflow-x-auto px-3 py-2"
            >
              {fotos.map((f, i) => {
                const marcada = seleccion.has(f.id);
                const esActual = i === posicion;
                return (
                  <button
                    key={f.id}
                    type="button"
                    // Sin esto, Shift+clic además selecciona el texto de la página.
                    onMouseDown={(e) => e.shiftKey && e.preventDefault()}
                    onClick={(e) => alTocarMiniatura(i, e)}
                    aria-label={t.miniatura(i + 1, fotos.length, f.nombre_invitado)}
                    aria-current={esActual ? "true" : undefined}
                    aria-pressed={seleccionando ? marcada : undefined}
                    className={
                      "relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border-2 transition " +
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-acento " +
                      (marcada
                        ? "border-acento"
                        : esActual
                          ? "border-white"
                          : "border-transparent opacity-60 hover:opacity-100")
                    }
                  >
                    <img
                      src={f.url}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      draggable={false}
                      className="h-full w-full object-cover"
                    />
                    {seleccionando && (
                      <span className="absolute bottom-1 right-1">
                        <Tilde marcada={marcada} />
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Botones para el dedo o el mouse, abajo, al alcance del pulgar. Los
              atajos de teclado siguen andando; esto es para revisar desde el
              celular, que no tiene teclado. */}
          <div className={`sticky bottom-0 z-20 shrink-0 border-t px-3 py-3 ${BARRA}`}>
            <div className="mx-auto max-w-xl">
              {seleccionando ? (
                <div className="grid grid-cols-2 gap-2">
                  <Boton
                    variante="peligro"
                    icono={XMarkIcon}
                    className={COMPACTO}
                    disabled={marcadas === 0}
                    onClick={() => alActuar("rechazar")}
                  >
                    {marcadas > 0 ? t.rechazarN(marcadas) : t.rechazar}
                  </Boton>
                  <Boton
                    icono={CheckIcon}
                    className={COMPACTO}
                    disabled={marcadas === 0}
                    onClick={() => alActuar("aprobar")}
                  >
                    {marcadas > 0 ? t.aprobarN(marcadas) : t.aprobar}
                  </Boton>
                </div>
              ) : (
                <div className="grid grid-cols-[1fr_auto_1fr] gap-2">
                  <Boton
                    variante="peligro"
                    icono={XMarkIcon}
                    className={COMPACTO}
                    onClick={() => alActuar("rechazar")}
                  >
                    {t.rechazar}
                  </Boton>
                  <Boton
                    variante="secundario"
                    icono={ArrowUturnLeftIcon}
                    className={COMPACTO}
                    disabled={decisiones === 0}
                    onClick={() => alActuar("deshacer")}
                  >
                    {t.deshacer}
                  </Boton>
                  <Boton icono={CheckIcon} className={COMPACTO} onClick={() => alActuar("aprobar")}>
                    {t.aprobar}
                  </Boton>
                </div>
              )}
              <AyudaTeclado seleccionando={seleccionando} />
            </div>
          </div>
        </>
      ) : (
        <Vacio icono={PhotoIcon} titulo={t.vacio.titulo} texto={t.vacio.texto}>
          <Boton onClick={() => navegar(lista.a)}>{t.volverA(lista.texto)}</Boton>
          {/* Si la última se aprobó sin querer, en el celular no hay Z. */}
          {decisiones > 0 && (
            <Boton variante="secundario" icono={ArrowUturnLeftIcon} onClick={deshacer}>
              {t.deshacer}
            </Boton>
          )}
        </Vacio>
      )}

      <Confirmar
        abierto={confirmarTodas}
        titulo={t.confirmarTodas.titulo(fotos.length)}
        mensaje={
          <>
            <p>{t.confirmarTodas.mensaje}</p>
            {enEspera.length > 0 && <p className="mt-2">{t.confirmarTodas.sinLasNuevas(enEspera.length)}</p>}
          </>
        }
        textoConfirmar={t.confirmarTodas.confirmar(fotos.length)}
        iconoConfirmar={AprobarTodasGrande}
        onConfirmar={aprobarTodas}
        onCancelar={() => setConfirmarTodas(false)}
      />
    </div>
  );
}

/**
 * El círculo de selección de iOS: vacío si no está marcada, azul con tilde
 * blanca si sí. Sobre una foto tiene que leerse igual en una clara que en una
 * oscura.
 *
 * La marcada es CheckCircleIcon (24/solid) en azul sobre un círculo blanco
 * del tamaño de la caja: la tilde del ícono es un hueco, y por ahí se ve el
 * blanco de atrás; el ícono dibuja su círculo un poco más chico que la caja, y
 * lo que sobra queda como el borde blanco de iOS.
 */
function Tilde({ marcada, grande = false }: { marcada: boolean; grande?: boolean }) {
  const tamano = grande ? "h-7 w-7" : "h-5 w-5";
  if (marcada) {
    return (
      <span aria-hidden className={`block rounded-full bg-white shadow shadow-black/40 ${tamano}`}>
        <CheckCircleIcon aria-hidden className="h-full w-full text-acento" />
      </span>
    );
  }
  return (
    <span
      aria-hidden
      className={`block rounded-full border-2 border-white/90 bg-black/30 shadow shadow-black/40 ${tamano}`}
    />
  );
}

/** Lo que va en lugar de la bandeja cuando no hay nada que revisar: no quedan
 *  pendientes, o las fotos ya se borraron. El ícono grande y tenue, como los
 *  estados vacíos de iOS; abajo, adónde ir. */
function Vacio({
  icono: IconoVacio,
  titulo,
  texto,
  children,
}: {
  icono: Icono;
  titulo: string;
  texto: string;
  children: ReactNode;
}) {
  return (
    <section className="flex min-h-[45vh] flex-1 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <IconoVacio aria-hidden className="mb-2 h-12 w-12 shrink-0 text-tenue" />
      <h2 className="text-balance text-2xl font-semibold">{titulo}</h2>
      <p className="text-balance text-tenue">{texto}</p>
      <div className="mt-6 flex w-full max-w-xs flex-col gap-3">{children}</div>
    </section>
  );
}

function Tecla({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex min-w-6 items-center justify-center rounded-md border border-borde bg-hundido px-1.5 py-0.5 font-sans text-xs text-white">
      {children}
    </kbd>
  );
}

/** Sólo en pantallas anchas: en un celular o una tablet no hay teclado y la
 *  ayuda sería una línea de ruido. */
function AyudaTeclado({ seleccionando }: { seleccionando: boolean }) {
  const a = t.ayuda;
  return (
    <p className="mt-2 hidden flex-wrap items-center justify-center gap-x-4 gap-y-1 text-sm text-tenue lg:flex"
    >
      <span>
        <Tecla>←</Tecla> <Tecla>→</Tecla> {a.moverte}
      </span>
      <span>
        <Tecla>A</Tecla> {a.aprobar}
      </span>
      <span>
        <Tecla>R</Tecla> {a.rechazar}
      </span>
      <span>
        <Tecla>Z</Tecla> {a.deshacer}
      </span>
      <span>
        <Tecla>{a.teclaShift}</Tecla> + {a.clic} {a.varias}
      </span>
      {seleccionando && (
        <span>
          <Tecla>{a.teclaEsc}</Tecla> {a.cancelar}
        </span>
      )}
    </p>
  );
}
