"""
Editor de personaje OFFLINE para Minecraft Dungeons II (version Xbox / PC Game Pass).

- Solo edita personajes con "IsOnline": false. Los online no se tocan.
- Hace copia de seguridad automatica antes de cada guardado (carpeta backups/).
- No guarda si el juego esta abierto.

Uso: doble clic en "Abrir editor.bat"  o  python editor_mcd2.py
Opciones:  --info            muestra el resumen y sale
           --wgs <carpeta>   usar otra carpeta de partidas (para pruebas con una copia)
"""
import copy
import datetime
import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import uuid

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(SCRIPT_DIR, "backups")
PACKAGES_GLOB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages",
                             "Microsoft.MinecraftDungeons2_*", "SystemAppData", "wgs", "*")
GAME_PROCESSES = {"dungeons.exe", "dungeons-wingdk-shipping.exe", "gamelaunchhelper.exe"}

ATTRIBUTE_NAMES = {
    "Emeralds": "Esmeraldas",
    "SpringStone": "Springstone",
    "EnchantmentPoints": "Puntos de encantamiento",
    "Level": "Nivel",
    "XP": "Experiencia (XP)",
    "VillageMerchantUpgradeLevel": "Mejora del mercader de la aldea",
    "VillageMerchantRefreshCharges": "Recargas del mercader",
    "EnchantsmithUpgradeLevel": "Mejora del encantador",
    "OldBlacksmithUpgradeLevel": "Mejora del herrero",
}
# Topes comprobados en el juego (lo que pase de aqui el juego lo recorta al cargar)
ATTRIBUTE_CAPS = {"Emeralds": 9999}
RARITY_NAMES = {"Common": "Comun", "Rare": "Raro", "Special": "Especial", "Unique": "Unico", "None": "-"}


# ---------------------------------------------------------------------------
# JSON que conserva los numeros decimales exactamente como los escribio el juego
# ---------------------------------------------------------------------------
class RawNum(float):
    """Un float que recuerda su texto original ("4100.0001169648413")."""
    def __new__(cls, text):
        obj = super().__new__(cls, text)
        obj.text = text
        return obj


def json_load(data: bytes):
    return json.loads(data.decode("utf-8"), parse_float=RawNum)


def json_dump(obj) -> str:
    if isinstance(obj, RawNum):
        return obj.text
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if obj is None:
        return "null"
    if isinstance(obj, (int, float, str)):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, list):
        return "[" + ",".join(json_dump(v) for v in obj) + "]"
    if isinstance(obj, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + json_dump(v)
                              for k, v in obj.items()) + "}"
    raise TypeError(f"Tipo no soportado: {type(obj)}")


# ---------------------------------------------------------------------------
# Formato de partidas de Xbox (wgs): containers.index -> container.N -> archivo
# ---------------------------------------------------------------------------
def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0], o + 4


def _str(b, o):
    n, o = _u32(b, o)
    return b[o:o + 2 * n].decode("utf-16-le"), o + 2 * n


def parse_index(wgs_dir):
    b = open(os.path.join(wgs_dir, "containers.index"), "rb").read()
    o = 0
    _version, o = _u32(b, o)
    count, o = _u32(b, o)
    o += 4                      # desconocido
    _pkg, o = _str(b, o)
    o += 8 + 4                  # fecha + desconocido
    _store_id, o = _str(b, o)
    o += 8                      # desconocido
    entries = []
    for _ in range(count):
        name, o = _str(b, o)
        _name2, o = _str(b, o)
        _etag, o = _str(b, o)
        num = b[o]
        o += 1 + 4
        folder = uuid.UUID(bytes_le=b[o:o + 16]).hex.upper()
        o += 16 + 8 + 8         # guid + fecha + desconocido
        size = struct.unpack_from("<Q", b, o)[0]
        entries.append({"name": name, "num": num, "folder": folder, "size": size, "size_offset": o})
        o += 8
    if o != len(b):
        raise ValueError("containers.index tiene un formato inesperado; no se toca nada.")
    return entries


def blob_path(wgs_dir, entry):
    folder = os.path.join(wgs_dir, entry["folder"])
    b = open(os.path.join(folder, f"container.{entry['num']}"), "rb").read()
    _version, count = struct.unpack_from("<II", b, 0)
    if count != 1:
        raise ValueError(f"El contenedor {entry['name']} tiene {count} archivos; se esperaba 1.")
    o = 8 + 128                 # nombre de archivo (64 caracteres utf-16)
    for guid_bytes in (b[o:o + 16], b[o + 16:o + 32]):
        path = os.path.join(folder, uuid.UUID(bytes_le=guid_bytes).hex.upper())
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"No se encontro el archivo de datos de {entry['name']}.")


def find_characters(wgs_dir):
    chars = []
    for entry in parse_index(wgs_dir):
        if not entry["name"].startswith("Character"):
            continue
        save = json_load(open(blob_path(wgs_dir, entry), "rb").read())
        chars.append((entry["name"], save))
    return chars


def write_character(wgs_dir, container_name, save):
    """Escribe la partida y actualiza el tamano en containers.index."""
    data = json_dump(save).encode("utf-8")
    entry = next(e for e in parse_index(wgs_dir) if e["name"] == container_name)
    path = blob_path(wgs_dir, entry)

    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)

    if entry["size"] != len(data):
        index_path = os.path.join(wgs_dir, "containers.index")
        b = bytearray(open(index_path, "rb").read())
        struct.pack_into("<Q", b, entry["size_offset"], len(data))
        with open(index_path + ".tmp", "wb") as f:
            f.write(b)
        os.replace(index_path + ".tmp", index_path)

    # Verificacion: volver a leer y comparar
    check = json_load(open(blob_path(wgs_dir, entry), "rb").read())
    if json_dump(check) != json_dump(save):
        raise RuntimeError("La verificacion fallo despues de guardar. Restaura la ultima copia.")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def game_is_running():
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    except OSError:
        return False
    running = {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line}
    return bool(running & GAME_PROCESSES)


def make_backup(wgs_dir, label):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"{stamp}_{label}", os.path.basename(wgs_dir))
    shutil.copytree(wgs_dir, dest)
    return os.path.dirname(dest)


def list_backups():
    found = glob.glob(os.path.join(BACKUP_DIR, "*", "containers.index"))
    found += glob.glob(os.path.join(BACKUP_DIR, "*", "*", "containers.index"))
    return sorted(os.path.dirname(index) for index in found)


def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def ask_number(prompt, current, allow_float=False):
    raw = ask(f"{prompt} (actual: {fmt(current)}, Enter = no cambiar): ")
    if not raw:
        return None
    try:
        value = float(raw) if allow_float else int(raw)
    except ValueError:
        print("  Numero no valido.")
        return None
    if value < 0:
        print("  No se permiten numeros negativos.")
        return None
    return value


def fmt(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def short(tag, prefix):
    return tag[len(prefix):] if tag.startswith(prefix) else tag


# ---------------------------------------------------------------------------
# Vistas y ediciones sobre el personaje
# ---------------------------------------------------------------------------
def attributes(save):
    return save["CharacterSaveV1"]["Ability"]["Attributes"]


def get_attr(save, name):
    return next((a for a in attributes(save) if a["AttributeName"] == name), None)


def item_label(entry):
    data = entry["ItemData"]
    name = short(data["TypeTag"], "SW.Item.")
    rarity = RARITY_NAMES.get(short(data["RarityTag"], "SW.Rarity."), data["RarityTag"])
    power = data.get("GeneratorData", {}).get("PowerGeneratorValues", {}).get("ItemPower")
    equipped = " [EQUIPADO]" if entry.get("EquippedSlot", "None") != "None" else ""
    enchants = []
    for eff in data.get("Effects", []):
        for sub in eff.get("EffectsInThisBatch", [eff]):
            enchants.append(short(sub.get("TypeTag", "?"), "SW.Effect."))
    text = f"{name:<32} {rarity:<9} poder {fmt(power) if power is not None else '-':>4}{equipped}"
    if enchants:
        text += "  | " + ", ".join(enchants)
    return text


def show_summary(save):
    meta = save["CharacterSaveV1"]["MetaData"]
    estado = "OFFLINE" if meta.get("IsOnline") is False else "ONLINE"
    print(f"\nPersonaje {meta['CharacterId']}  [{estado}]")
    print(f"  Nivel {meta.get('Level')} | Poder {meta.get('PowerLevel')} | Zona: {meta.get('CurrentLocation')}")
    print("  Recursos y atributos:")
    for a in attributes(save):
        label = ATTRIBUTE_NAMES.get(a["AttributeName"], a["AttributeName"])
        print(f"    - {label:<34} {fmt(a['CurrentValue'])}")


def show_inventory(save):
    entries = save["CharacterSaveV1"]["Inventory"]["Entries"]
    print(f"\nInventario ({len(entries)} objetos):")
    for i, entry in enumerate(entries, 1):
        print(f"  {i:>3}. {item_label(entry)}")


def edit_attr(save, name, allow_float=False):
    attr = get_attr(save, name)
    if attr is None:
        print(f"  Este personaje no tiene el atributo {name}.")
        return False
    label = ATTRIBUTE_NAMES.get(name, name)
    value = ask_number(label, attr["CurrentValue"], allow_float)
    if value is None:
        return False
    cap = ATTRIBUTE_CAPS.get(name)
    if cap is not None and value > cap:
        print(f"  El juego no permite mas de {cap}; se pone {cap}.")
        value = cap
    attr["CurrentValue"] = value
    if name == "Level":
        save["CharacterSaveV1"]["MetaData"]["Level"] = int(value)
    print(f"  {label} -> {fmt(value)} (falta guardar con la opcion 9)")
    return True


def edit_other_attr(save):
    attrs = attributes(save)
    for i, a in enumerate(attrs, 1):
        print(f"  {i}. {ATTRIBUTE_NAMES.get(a['AttributeName'], a['AttributeName'])}: {fmt(a['CurrentValue'])}")
    choice = ask("Numero del atributo: ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(attrs):
        return False
    attr = attrs[int(choice) - 1]
    return edit_attr(save, attr["AttributeName"], allow_float=isinstance(attr["CurrentValue"], float))


def pick_item(save):
    show_inventory(save)
    entries = save["CharacterSaveV1"]["Inventory"]["Entries"]
    choice = ask("Numero del objeto (Enter = cancelar): ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(entries):
        return None
    return entries[int(choice) - 1]


def edit_item_power(save):
    entry = pick_item(save)
    if entry is None:
        return False
    values = entry["ItemData"].get("GeneratorData", {}).get("PowerGeneratorValues")
    if not values or "ItemPower" not in values:
        print("  Este objeto no tiene poder (por ejemplo, cosmeticos).")
        return False
    value = ask_number("Nuevo poder", values["ItemPower"])
    if value is None:
        return False
    values["ItemPower"] = value
    if values.get("ItemPowerMax", 0) < value:
        values["ItemPowerMax"] = value
    print(f"  Poder -> {value} (EXPERIMENTAL: el juego podria recalcularlo). Falta guardar con la opcion 9.")
    return True


def duplicate_item(save):
    entry = pick_item(save)
    if entry is None:
        return False
    clone = copy.deepcopy(entry)
    clone["EquippedSlot"] = "None"
    save["CharacterSaveV1"]["Inventory"]["Entries"].append(clone)
    print(f"  Duplicado: {item_label(clone)} (falta guardar con la opcion 9)")
    return True


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def choose_wgs_dir(override):
    if override:
        return os.path.normpath(override)
    dirs = [d for d in glob.glob(PACKAGES_GLOB) if os.path.exists(os.path.join(d, "containers.index"))]
    if not dirs:
        sys.exit("No encontre partidas de Minecraft Dungeons II (version Xbox / Game Pass) en este PC.")
    if len(dirs) == 1:
        return dirs[0]
    for i, d in enumerate(dirs, 1):
        print(f"  {i}. {os.path.basename(d)}")
    choice = ask("Hay varias cuentas de Xbox. Elige una: ")
    return dirs[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= len(dirs) else sys.exit(0)


def choose_character(wgs_dir):
    chars = find_characters(wgs_dir)
    if not chars:
        sys.exit("No hay personajes guardados en esta cuenta.")
    if len(chars) == 1:
        return chars[0]
    for i, (_, save) in enumerate(chars, 1):
        meta = save["CharacterSaveV1"]["MetaData"]
        estado = "offline" if meta.get("IsOnline") is False else "online"
        print(f"  {i}. Nivel {meta.get('Level')} ({estado}) - {meta['CharacterId']}")
    choice = ask("Elige un personaje: ")
    return chars[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= len(chars) else sys.exit(0)


def save_changes(wgs_dir, container_name, save, label="antes-de-editar"):
    if save["CharacterSaveV1"]["MetaData"].get("IsOnline") is not False:
        print("  Este personaje no es offline. El editor solo guarda personajes offline.")
        return False
    if game_is_running():
        print("  El juego esta abierto. Cierralo por completo y vuelve a intentar.")
        return False
    backup = make_backup(wgs_dir, label)
    write_character(wgs_dir, container_name, save)
    print(f"  Guardado y verificado. Copia de seguridad en: {os.path.relpath(backup, SCRIPT_DIR)}")
    print("  Si al abrir el juego aparece un conflicto de sincronizacion, elige la partida de ESTE dispositivo.")
    return True


def restore_backup(wgs_dir, container_name, save):
    backups = list_backups()
    char_id = save["CharacterSaveV1"]["MetaData"]["CharacterId"]
    options = []
    for b in backups:
        try:
            for name, old in find_characters(b):
                if old["CharacterSaveV1"]["MetaData"]["CharacterId"] == char_id:
                    options.append((b, old))
        except (OSError, ValueError, StopIteration):
            continue
    if not options:
        print("  No hay copias de seguridad de este personaje.")
        return None
    for i, (b, old) in enumerate(options, 1):
        esm = get_attr(old, "Emeralds")
        print(f"  {i}. {os.path.relpath(b, BACKUP_DIR).split(os.sep)[0]}  "
              f"(nivel {old['CharacterSaveV1']['MetaData'].get('Level')}, "
              f"esmeraldas {fmt(esm['CurrentValue']) if esm else '-'})")
    choice = ask("Cual restaurar (Enter = cancelar): ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(options):
        return None
    old = options[int(choice) - 1][1]
    if old["CharacterSaveV1"]["MetaData"].get("IsOnline") is not False:
        print("  Esa copia no es de un personaje offline; no se restaura.")
        return None
    if save_changes(wgs_dir, container_name, old, "antes-de-restaurar"):
        return old
    return None


MENU = """
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
 0) Salir"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    override = args[args.index("--wgs") + 1] if "--wgs" in args else None

    wgs_dir = choose_wgs_dir(override)
    container_name, save = choose_character(wgs_dir)
    show_summary(save)
    if "--info" in args:
        return

    if save["CharacterSaveV1"]["MetaData"].get("IsOnline") is not False:
        print("\nEste personaje esta marcado como ONLINE. El editor no lo modifica,")
        print("pero con la opcion 10 puedes restaurar una copia de cuando era offline.")

    pending = False
    while True:
        print(MENU + ("\n   (hay cambios SIN guardar)" if pending else ""))
        op = ask("Opcion: ")
        if op == "1":
            show_summary(save)
        elif op == "2":
            pending |= edit_attr(save, "Emeralds")
        elif op == "3":
            pending |= edit_attr(save, "SpringStone")
        elif op == "4":
            pending |= edit_attr(save, "EnchantmentPoints")
        elif op == "5":
            pending |= edit_other_attr(save)
        elif op == "6":
            show_inventory(save)
        elif op == "7":
            pending |= edit_item_power(save)
        elif op == "8":
            pending |= duplicate_item(save)
        elif op == "9":
            if save_changes(wgs_dir, container_name, save):
                pending = False
        elif op == "10":
            restored = restore_backup(wgs_dir, container_name, save)
            if restored is not None:
                save, pending = restored, False
        elif op == "0":
            if pending and ask("Hay cambios sin guardar. Salir de todos modos? (s/n): ").lower() != "s":
                continue
            return


if __name__ == "__main__":
    main()
