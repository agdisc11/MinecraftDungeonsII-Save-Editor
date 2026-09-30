# Editor de personaje offline para Minecraft Dungeons II

Script para editar personajes **offline** de Minecraft Dungeons II en PC: esmeraldas, Springstone, nivel, poder de armas, duplicar objetos y más. Sirve para experimentar en tu propia partida sin conexión.

> **Proyecto de fans, no oficial.** No está afiliado ni respaldado por Mojang Studios ni Microsoft.

---

## ⚠️ Solo personajes offline

El editor **solo modifica personajes creados en modo offline** (`"IsOnline": false`).

- Los personajes online **no se guardan en tu PC**, viven en los servidores del juego, así que no hay nada que editar.
- **No intentes convertir un personaje offline en online** cambiando `IsOnline` a mano. El juego da el error **0038** al seleccionar el héroe, y el personaje queda inutilizable hasta restaurar una copia.

## Requisitos

- Windows 10 u 11
- Minecraft Dungeons II instalado desde la **app de Xbox / PC Game Pass**
  (la versión de Steam guarda las partidas en otro lugar y **no está probada**)
- [Python 3.8 o superior](https://www.python.org/downloads/). Marca la casilla *"Add Python to PATH"* al instalarlo. No necesita librerías extra.

## Uso

1. **Cierra el juego por completo.** Revisa el Administrador de tareas (`Ctrl+Shift+Esc`): a veces se queda abierto en segundo plano.
2. Haz doble clic en **`Abrir editor.bat`**.
3. Elige lo que quieras cambiar en el menú.
4. Usa la opción **9 (GUARDAR)**. Hasta ese momento no se modifica nada.
5. Abre el juego. Si Xbox pregunta qué partida conservar, elige la de **este dispositivo**.

```
===== Editor OFFLINE - Minecraft Dungeons II =====
 1) Ver recursos y atributos
 2) Cambiar esmeraldas
 3) Cambiar Springstone
 4) Cambiar puntos de encantamiento
 5) Cambiar otro atributo (nivel, XP, mercaderes...)
 6) Ver inventario
 7) Cambiar poder de un objeto   (experimental)
 8) Duplicar un objeto           (experimental)
 9) GUARDAR cambios en la partida
10) Restaurar una copia de seguridad
 0) Salir
```

## Qué se puede editar

| Qué | Estado | Notas |
|---|---|---|
| Esmeraldas | ✅ Probado | El juego tiene un **tope de 9999**. Si pones más, lo recorta al cargar (el editor ya lo limita). |
| Springstone | ✅ Probado | |
| Nivel del personaje | ✅ Probado | |
| Poder de armas | ✅ Probado | Probado en armas equipadas. |
| Puntos de encantamiento | ❔ Sin probar | Se guardan bien, pero falta comprobarlos en el juego. |
| Mejoras de mercaderes | ❔ Sin probar | |
| Duplicar objetos | 🧪 Experimental | |

*Probado con la versión de lanzamiento (29/09/2026), app de Xbox, Windows 11.*

## Copias de seguridad

- **Antes de cada guardado** el editor copia tu partida completa a `backups/<fecha>_<motivo>/`.
- Con la **opción 10** puedes volver a cualquier copia. Antes de restaurar se guarda también el estado actual.
- La carpeta `backups/` contiene los tokens de tu cuenta de Xbox. **No la compartas ni la subas a ningún sitio.**

## Protecciones

- No guarda si el juego está abierto.
- No modifica personajes online.
- Después de guardar vuelve a leer la partida para comprobar que quedó bien.
- Si no cambias nada, la partida queda idéntica byte por byte, porque conserva el formato exacto de los números del juego.

## Cómo funciona (técnico)

Las partidas de la versión Xbox usan el sistema de guardado en la nube de Xbox (WGS):

```
%LOCALAPPDATA%\Packages\Microsoft.MinecraftDungeons2_8wekyb3d8bbwe\SystemAppData\wgs\<cuenta>\
├── containers.index          ← índice: nombre, carpeta y TAMAÑO de cada contenedor
├── <carpeta-contenedor>\
│   ├── container.N           ← apunta al archivo de datos actual (N cambia al guardar)
│   └── <archivo-de-datos>    ← el personaje: JSON sin cifrar
└── ...
```

- Cada personaje es un contenedor llamado `Character<id>`. Sus datos son JSON (`FCharacterSaveV1`) con `MetaData`, `Ability.Attributes`, `Inventory.Entries`, etc.
- `containers.index` guarda el **tamaño** de cada contenedor. Si editas el JSON a mano y el tamaño cambia, hay que actualizarlo. El editor lo hace automáticamente.
- El nombre del archivo de datos **cambia cada vez que el juego guarda**. El editor lo busca cada vez a través del índice.
- Los contenedores `entitlementsjwtbin`, `auth_dynamic_entjwtbin` y `Guidbin` son tokens de tu cuenta. El editor **no los toca**.

## Problemas comunes

| Problema | Solución |
|---|---|
| "El juego está abierto" | Ciérralo desde el Administrador de tareas (`Dungeons-WinGDK-Shipping.exe`). |
| "No encontré partidas" | Solo funciona con la versión de la app de Xbox / Game Pass. |
| Error 0038 al elegir el héroe | La partida se modificó mal (por ejemplo, `IsOnline` cambiado a mano). Restaura una copia con la opción 10. |
| Aparecen los valores de antes | Al abrir el juego elegiste la partida de la nube. Vuelve a guardar y elige **este dispositivo**. |

## Aviso

- Úsalo bajo tu propio riesgo y **solo en partidas offline**. No está pensado para ventajas en el juego online.
- Minecraft y Minecraft Dungeons son marcas registradas de Mojang Studios / Microsoft.

---

## English summary

Offline character editor for **Minecraft Dungeons II** (PC, Xbox app / Game Pass version). It edits emeralds (capped at 9999 by the game), Springstone, level, weapon power and more, and it only works on **offline** characters, since online characters live server-side. It takes an automatic backup before every save, refuses to write while the game is running, and keeps no-op saves byte-identical. Requires Python 3.8+ with no dependencies. Run `Abrir editor.bat`. Unofficial fan project, not affiliated with Mojang or Microsoft.
