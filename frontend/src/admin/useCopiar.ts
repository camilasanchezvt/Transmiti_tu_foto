import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Copiar al portapapeles, con el "Copiado" de un momento en el botón.
 *
 * Sin permiso (http sin candado, algunos navegadores de celular) el texto se
 * muestra en un cuadro para copiarlo a mano: `aMano` es lo que dice ese cuadro
 * arriba del texto.
 *
 *   const [copiado, copiar] = useCopiar();
 *   <BotonChico onClick={() => copiar(link, "Copiá este link")}>…</BotonChico>
 */
export function useCopiar(): [boolean, (valor: string, aMano: string) => void] {
  const [copiado, setCopiado] = useState(false);
  const temporizador = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(temporizador.current), []);

  const copiar = useCallback(async (valor: string, aMano: string) => {
    try {
      await navigator.clipboard.writeText(valor);
    } catch {
      window.prompt(aMano, valor);
      return;
    }
    setCopiado(true);
    window.clearTimeout(temporizador.current);
    temporizador.current = window.setTimeout(() => setCopiado(false), 1500);
  }, []);

  return [copiado, copiar];
}

export default useCopiar;
