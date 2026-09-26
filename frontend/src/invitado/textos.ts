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
  // Con una sola foto permitida, "tus 1 fotos" no se dice.
  errorLimite: (cuantas: number) =>
    cuantas === 1 ? "Ya mandaste tu foto. ¡Gracias!" : `Ya mandaste tus ${cuantas} fotos. ¡Gracias!`,
  // Muchos invitados en el mismo wifi del salón cuentan como uno solo para el
  // tope de pedidos. Lo que ve el invitado es que hay que esperar un poco.
  errorMuchas: "Están llegando muchas fotos juntas. Esperá un minuto y probá de nuevo",
  eventoCerrado: "Este evento ya terminó",

  // Si la página no abre, el invitado todavía no mandó nada: "no pudimos
  // subirla" no tiene sentido ahí. Debajo va el botón "Probar de nuevo".
  errorCarga: "No pudimos abrir el evento. Revisá tu señal y probá de nuevo",
  // Un evento sin publicar responde igual que uno que no existe. Lo más común
  // es que alguien escanee el QR impreso antes de que arranque.
  eventoNoEncontrado: "No encontramos este evento. Si todavía no empezó, probá en un rato",

  // El nombre es opcional a propósito: pedirlo obligatorio agrega un paso a algo
  // que tiene que salir de un toque. Se aclara dónde va a aparecer: sale en la
  // pared, debajo de la foto, delante de todos.
  etiquetaNombre: "Tu nombre en la pantalla (si querés)",
  ejemploNombre: "Sofi",
} as const;
