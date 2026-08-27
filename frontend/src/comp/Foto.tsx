import { useState } from "react";

interface Props {
  url: string;
  ancho?: number | null;
  alto?: number | null;
  alt?: string;
  className?: string;
  onError?: () => void;
}

/**
 * Nunca deforma la foto: entra completa y centrada. El espacio que sobra se
 * llena con la misma imagen ampliada y desenfocada, que en un proyector se ve
 * mucho mejor que una banda negra.
 */
export default function Foto({ url, ancho, alto, alt = "", className = "", onError }: Props) {
  const [rota, setRota] = useState(false);

  if (rota) return null;

  return (
    <div className={`relative h-full w-full overflow-hidden bg-fondo ${className}`}>
      <div
        aria-hidden
        className="absolute inset-0 scale-110 bg-cover bg-center blur-2xl brightness-50"
        style={{ backgroundImage: `url(${JSON.stringify(url)})` }}
      />
      <img
        src={url}
        alt={alt}
        width={ancho ?? undefined}
        height={alto ?? undefined}
        onError={() => {
          setRota(true);
          onError?.();
        }}
        className="relative h-full w-full object-contain"
      />
    </div>
  );
}
