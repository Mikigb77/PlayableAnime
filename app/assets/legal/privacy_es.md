## Quiénes somos

Lucid Saga es un juego de historias con IA creado por [nombre del responsable], [dirección]. Para cualquier
cuestión sobre tus datos, escribe a [email de contacto de privacidad]. Respondemos en el plazo de un mes.

## Qué recogemos y por qué

| Qué | Por qué | Base jurídica |
| --- | --- | --- |
| **Cuenta:** email, nombre visible, fecha de nacimiento y, o bien una contraseña (guardada solo como hash con sal), o bien el ID de tu cuenta de Google | Para iniciar tu sesión, que tus historias sigan siendo tuyas y aplicar las reglas de edad: solo historias juveniles por debajo de los 17 años | Contrato |
| **Ajustes de las historias y preferencias de contenido:** nivel de gore, romance y temas oscuros activados o no | Para dar forma a las historias que recibes | Contrato |
| **Tus historias:** la premisa, las acciones que escribes o dictas, las opciones que eliges y lo que el narrador responde | Esto es el juego: cada turno envía la historia hasta ese momento al modelo de IA para que escriba lo que pasa después | Contrato |
| **Imágenes** creadas para tus historias | Se muestran en tus historias, creadas en los momentos clave | Contrato |
| **Escenas leídas en voz alta:** el audio que la voz de estudio hizo de tus escenas | Para que una escena que vuelves a oír suene al instante y no cueste nada | Contrato |
| **Créditos:** tu saldo y lo que costó cada turno, imagen, dictado o escena leída en voz alta | Para cobrar de forma justa y mostrarte tu gasto | Contrato |
| **Dispositivos con sesión iniciada:** cuándo inició sesión cada uno y cuándo se usó por última vez | Para mantener tu sesión y dejarte cerrar la sesión de un dispositivo | Contrato |
| **Registros técnicos:** identificadores de petición, el ID de tu cuenta, el ID de la historia, errores, tiempos, costes por turno, y cuándo nuestras reglas de seguridad bloquearon una escena y en qué categoría (nunca el texto de la historia) | Para que el servicio funcione, corregir errores y controlar los costes | Interés legítimo |
| **Denuncias:** la escena que denunciaste, el motivo que elegiste, cualquier nota que escribiste, si bloqueaste la escena y lo que decidió nuestro equipo | Para revisar escenas que puedan incumplir nuestras reglas de contenido, corregir al narrador y mantener oculta una escena que bloqueaste | Interés legítimo |
| **Protección del inicio de sesión:** recuentos de corta duración de inicios de sesión fallidos por email y por dirección de red, guardados solo como claves de un solo sentido, nunca el email ni la dirección | Para impedir que se adivinen contraseñas y que se creen registros falsos | Interés legítimo |

Nunca vendemos tus datos, no te mostramos anuncios y no usamos tus historias para entrenar modelos
de IA.

## Voz

Cuando tocas el micrófono, lo que dices se convierte en texto en el cuadro, para que lo revises
antes de enviarlo (V5). En Cuenta, en Dictado, eliges qué lo pasa a texto:

- **En línea (la opción por defecto).** La aplicación graba mientras el micrófono está encendido y
  envía la grabación a nuestro servidor, que hace que Gemini, en Vertex AI de Google Cloud, la
  pase a texto, atento a los nombres que tu personaje conoce en esa historia. La grabación se usa
  solo para esa petición: nunca la guardamos ni la registramos, y Google no la usa para entrenar
  sus modelos. Solo guardamos su duración y su coste, como un movimiento de tu historial de
  créditos.
- **Este dispositivo.** El reconocedor de voz de tu propio teléfono lo pasa a texto, y el audio
  nunca llega a nuestros servidores. Android usa el servicio de reconocimiento de voz de Google en
  tu teléfono; los teléfonos recientes reconocen la voz en el propio dispositivo. iOS usa el
  reconocimiento de voz de Apple: si tu iPhone admite el reconocimiento en el dispositivo para tu
  idioma, el audio se queda en el teléfono; si no, Apple lo procesa en sus servidores.

El texto forma parte de tu historia como cualquier cosa que escribas. La aplicación pide permiso
para usar el micrófono la primera vez que lo tocas, el micrófono solo está encendido mientras
muestra que está escuchando, y escribir siempre funciona.

Cuando pulsas reproducir en una escena, se lee en voz alta. En Cuenta, en Lectura en voz alta,
eliges la voz (V9):

- **Voz de estudio (la opción por defecto).** Nuestro servidor envía el texto de la escena a
  Gemini, en Vertex AI de Google Cloud, que lo lee en voz alta, y guarda el audio con tu historia,
  así que volver a oír la escena es gratis. Google no usa el texto para entrenar sus modelos. El
  audio se borra con la historia o con tu cuenta.
- **Este dispositivo.** La voz propia de tu dispositivo lee la escena, y nada llega a nuestros
  servidores. Algunos motores, como el de Google en Android, pueden usar voces en línea para un
  idioma que el teléfono no ha descargado.

## Quién trata tus datos por nosotros

| Servicio | Qué hace | Dónde |
| --- | --- | --- |
| Google Cloud: Cloud Run, Cloud Storage, Cloud Logging, Secret Manager | Ejecuta el servidor del juego y guarda las imágenes, el audio de las escenas leídas en voz alta y los registros | UE: Fráncfort |
| Google Cloud: Vertex AI (Gemini) | Escribe la historia, dibuja las imágenes, pasa a texto el dictado en línea y lee las escenas en voz alta con la voz de estudio. Google no usa estos datos para entrenar sus modelos. La parte de las instrucciones de una historia que no cambia de un turno a otro (su estilo, sus ajustes de contenido y su mundo) se guarda en una caché de Vertex AI hasta 15 minutos después de tu último turno, para que cueste menos | [Endpoint global, posiblemente fuera de la UE, o una región de la UE: ver la pregunta abierta 3] |
| Neon | Aloja la base de datos | Fráncfort (AWS eu-central-1) |
| Google Sign-In | Confirma quién eres cuando inicias sesión con Google | Google |

Cuando los datos salen de la UE, lo hacen al amparo de las cláusulas contractuales tipo de la
Comisión Europea o del Marco de Privacidad de Datos UE-EE. UU.

**Tu propia clave de API.** Si añades tu propia clave de API de Gemini, tus turnos van a la API de
Gemini de Google con tu propia cuenta y según las condiciones de Google para ella. El dictado en
línea y la voz de estudio siguen funcionando con nuestra cuenta. En el nivel gratuito de Gemini, Google puede usar lo que
envías para mejorar sus productos. La aplicación guarda la clave en tu dispositivo y la envía con
cada petición; nuestro servidor la usa solo para esa petición y nunca la guarda ni la registra.

## Cuánto tiempo lo guardamos

- **Tu cuenta, tus historias, tus imágenes y el audio de las escenas leídas en voz alta:** hasta
  que los elimines.
- **Denuncias:** hasta que elimines la historia o tu cuenta.
- **Eliminar tu cuenta** (Cuenta, Eliminar cuenta) borra tu cuenta, todas las historias, todas las
  imágenes y todos los dispositivos con sesión iniciada de la base de datos y el almacenamiento en
  uso, de inmediato. Las copias del historial de restauración de la base de datos desaparecen
  cuando caducan, en un plazo de [N] días.
- **Registros:** [30] días.

## Tus derechos

Puedes, en cualquier momento:

- **Descargar todo** lo que tenemos sobre ti en un archivo (Cuenta, Exportar mis datos).
- **Eliminar tu cuenta** y todo lo que contiene (Cuenta, Eliminar cuenta).
- **Corregir** tu nombre visible y tus preferencias en Cuenta, o pedirnos que corrijamos cualquier
  otra cosa.
- **Oponerte** al tratamiento basado en el interés legítimo, o pedirnos que lo limitemos.
- **Reclamar** ante una autoridad de protección de datos, como [la autoridad del país del
  responsable, por ejemplo la AEPD en España].

## Menores

Tienes que tener al menos [13] años para registrarte, y te pedimos la fecha de nacimiento al
hacerlo. Los jugadores menores de 17 años solo reciben historias juveniles, diga lo que diga la
clasificación por edades de la tienda. Si nos enteramos de que se registró alguien por debajo de
la edad mínima, eliminamos la cuenta.

## Seguridad

Todo el tráfico va cifrado. Las contraseñas se guardan solo como hashes con sal, los tokens de
sesión como hashes de un solo sentido, y nuestras propias claves y contraseñas están en Google
Secret Manager. Cerrar la sesión en un dispositivo la termina al instante, y los intentos repetidos
con una contraseña incorrecta se ralentizan.

En nuestras herramientas de administración, solo el propietario y el equipo que gestiona las
denuncias pueden leer el texto de las historias, y lo leen para revisar denuncias. El resto del
equipo, que ayuda con las cuentas y los créditos, ve el título, la clasificación y las cifras de una
historia, nunca lo que está escrito en ella.

## Cambios

Si esta política cambia de forma relevante, te lo diremos en la aplicación antes de que entre en
vigor.

*Última actualización: [fecha].*
