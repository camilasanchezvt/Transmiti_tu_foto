import { ArrowPathIcon, ExclamationTriangleIcon } from "@heroicons/react/24/outline";

import { ErrorApi } from "../api/client";
import Boton from "./Boton";
import { textosBase } from "./textos";

interface Props {
  error: unknown;
  onReintentar?: () => void;
}

/**
 * Muestra el mensaje que mandó el backend. Los mensajes del contrato ya están
 * escritos para que el invitado los lea tal cual, así que no se reescriben acá.
 *
 * Arriba va el triángulo naranja de aviso: se entiende que algo no salió antes
 * de leer. Naranja y no rojo, como en iOS: casi siempre alcanza con probar de
 * nuevo.
 */
export default function MensajeError({ error, onReintentar }: Props) {
  const mensaje = error instanceof ErrorApi ? error.message : textosBase.errorGenerico;

  return (
    <div className="flex flex-col items-center gap-4 p-8 text-center">
      <ExclamationTriangleIcon aria-hidden className="h-10 w-10 shrink-0 text-naranja" />
      <p className="text-xl leading-snug">{mensaje}</p>
      {onReintentar && (
        <div className="mt-2 w-full max-w-xs">
          <Boton variante="secundario" icono={ArrowPathIcon} onClick={onReintentar}>
            {textosBase.probarDeNuevo}
          </Boton>
        </div>
      )}
    </div>
  );
}
