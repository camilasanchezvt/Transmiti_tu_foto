// Todos los textos que ve el invitado. En español rioplatense, en segunda
// persona y cortos. Ninguno menciona palabras del sistema.
//
// Van acá y no incrustados en el JSX para poder revisarlos de una sola pasada:
// es la parte de la app que lee gente que no vio nunca el proyecto.

export const textos = {
  bienvenida: "Mandá tu foto y aparece en la pantalla",
  botonPrincipal: "Elegir foto",
  botonOtra: "Mandar otra",
  botonReintentar: "Probar de nuevo",

  preparando: "Preparando tu foto…",
  subiendo: (porcentaje: number) => `Subiendo… ${porcentaje}%`,

  listoTitulo: "¡Llegó!",
  listoDetalle: "En un rato la vas a ver en la pantalla",

  errorRed: "No pudimos subirla. Probá de nuevo",
  errorArchivo: "Sólo podemos recibir fotos",
  errorLimite: (cuantas: number) => `Ya mandaste tus ${cuantas} fotos. ¡Gracias!`,
  eventoCerrado: "Este evento ya terminó",

  // El nombre es opcional a propósito: pedirlo obligatorio agrega un paso a algo
  // que tiene que salir de un toque.
  etiquetaNombre: "Tu nombre (si querés)",
  ejemploNombre: "Sofi",
} as const;
