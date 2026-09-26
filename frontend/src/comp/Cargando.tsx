import { textosBase } from "./textos";

interface Props {
  texto?: string;
}

/** Para las esperas que no tienen progreso real. La subida NO usa esto: ahí va
 *  una barra con el progreso de verdad. */
export default function Cargando({ texto = textosBase.cargando }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 p-8 text-tenue">
      <div
        className="h-10 w-10 animate-spin rounded-full border-4 border-borde border-t-acento"
        role="status"
        aria-label={texto}
      />
      <p className="text-base">{texto}</p>
    </div>
  );
}
