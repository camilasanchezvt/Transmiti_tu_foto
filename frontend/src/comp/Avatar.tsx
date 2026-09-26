import { useState } from "react";

/**
 * La foto de una cuenta, en un círculo. Sin foto (o si no carga), las
 * iniciales sobre gris, como en los Contactos de iOS.
 *
 * Es decorativo: va siempre al lado del nombre, que es lo que lee un lector de
 * pantalla. Por eso no lleva alt ni texto propio.
 *
 *   <Avatar nombre={cuenta.nombre} url={cuenta.avatar_url} tamano="tarjeta" />
 *
 * Gris y no un color por persona: en Cuentas el color ya dice algo (naranja
 * espera, azul es admin) y un círculo naranja parecería una cuenta pendiente.
 */

export type TamanoAvatar = "barra" | "tarjeta" | "perfil";

const TAMANOS: Record<TamanoAvatar, { px: number; clase: string }> = {
  // Las iniciales, alrededor del 40% del círculo, como en iOS.
  barra: { px: 32, clase: "h-8 w-8 text-[13px]" },
  tarjeta: { px: 44, clase: "h-11 w-11 text-base" },
  perfil: { px: 80, clase: "h-20 w-20 text-3xl" },
};

interface Props {
  nombre: string;
  /** La de Cloudinary, un blob: de la vista previa, o null. */
  url: string | null | undefined;
  tamano?: TamanoAvatar;
  className?: string;
}

/**
 * Las iniciales del primer y el último nombre: "Ana Pérez" → "AP", "María de
 * los Ángeles" → "MÁ", "Bruno" → "B". Se saltea lo que no es letra ni número
 * ("(Ana)" → "A"). Por letras y no por unidades de UTF-16, así un nombre que
 * empieza con un emoji no queda partido al medio.
 */
export function iniciales(nombre: string): string {
  const palabras = nombre
    .trim()
    .split(/\s+/)
    .map((p) => Array.from(p).find((c) => /[\p{L}\p{N}]/u.test(c)))
    .filter((c): c is string => c !== undefined);
  if (palabras.length === 0) return "?";
  const letras = palabras.length === 1 ? [palabras[0]] : [palabras[0], palabras[palabras.length - 1]];
  return letras.join("").toLocaleUpperCase("es");
}

const TRAMO = "/image/upload/";

/**
 * La misma imagen, recortada al tamaño en que se muestra (x3, por las
 * pantallas de celular): la foto de perfil se sube de 512 px, y la lista de
 * Cuentas con veinte fotos así pesaría un mega sin necesidad.
 *
 * Sólo si la URL es la que devolvió la subida (…/image/upload/v123/avatares/…).
 * Si ya trae transformaciones, o no es de Cloudinary, va tal cual.
 */
export function urlAvatar(url: string, px: number): string {
  if (!url.startsWith("https://res.cloudinary.com/")) return url;
  const i = url.indexOf(TRAMO);
  if (i < 0) return url;
  const corte = i + TRAMO.length;
  const resto = url.slice(corte);
  if (!/^v\d+\//.test(resto)) return url;
  const lado = px * 3;
  return `${url.slice(0, corte)}c_fill,w_${lado},h_${lado},f_auto,q_auto/${resto}`;
}

export default function Avatar({ nombre, url, tamano = "tarjeta", className = "" }: Props) {
  const { px, clase } = TAMANOS[tamano];

  // Primero la achicada; si no carga (una cuenta de Cloudinary que no deja
  // transformar al vuelo), la original; si tampoco, las iniciales.
  const candidatas = url ? Array.from(new Set([urlAvatar(url, px), url])) : [];
  const [fallas, setFallas] = useState<{ url: string | null | undefined; n: number }>({ url, n: 0 });
  const n = fallas.url === url ? fallas.n : 0;
  const actual = candidatas[n];

  const base =
    "relative inline-flex shrink-0 select-none items-center justify-center overflow-hidden rounded-full " +
    `${clase} ${className}`;

  if (actual) {
    return (
      // El borde fino separa una foto clara del fondo claro (y una oscura del
      // oscuro): sin él, la cara parece flotar.
      <span aria-hidden className={`${base} border border-borde bg-hundido`}>
        <img
          key={actual}
          src={actual}
          alt=""
          width={px}
          height={px}
          decoding="async"
          draggable={false}
          onError={() => setFallas({ url, n: n + 1 })}
          className="h-full w-full object-cover"
        />
      </span>
    );
  }

  return (
    <span aria-hidden className={`${base} bg-hundido font-semibold leading-none text-texto`}>
      {iniciales(nombre)}
    </span>
  );
}
