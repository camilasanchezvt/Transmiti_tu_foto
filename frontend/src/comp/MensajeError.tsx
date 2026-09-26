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
 */
export default function MensajeError({ error, onReintentar }: Props) {
  const mensaje = error instanceof ErrorApi ? error.message : textosBase.errorGenerico;

  return (
    <div className="flex flex-col items-center gap-6 p-8 text-center">
      <p className="text-xl leading-snug">{mensaje}</p>
      {onReintentar && (
        <div className="w-full max-w-xs">
          <Boton variante="secundario" onClick={onReintentar}>
            {textosBase.probarDeNuevo}
          </Boton>
        </div>
      )}
    </div>
  );
}
