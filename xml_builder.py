
import logging
import xml.etree.ElementTree as ET

import config

logger = logging.getLogger(__name__)

_VALUE_RANGES = {
    "uiCopies": (1, 999),
    "byPlatenSize": (0, 4),
    "byInk": (0, 2),
    "byResolution": (1, 1),
    "byHighlight": (1, 9),
    "byMask": (1, 5),
    "byInkVolume": (1, 10),
    "byDoublePrint": (0, 3),
    "byTolerance": (0, 50),
    "byMinWhite": (1, 6),
    "byChoke": (0, 10),
    "bySaturation": (0, 40),
    "byBrightness": (0, 40),
    "byContrast": (0, 40),
    "iCyanBalance": (-5, 5),
    "iMagentaBalance": (-5, 5),
    "iYellowBalance": (-5, 5),
    "iBlackBalance": (-5, 5),
}


def _clamped(tag: str, value: str) -> str:
    bounds = _VALUE_RANGES.get(tag)
    if not bounds:
        return value
    low, high = bounds
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        logger.warning("XML %s 값 %r 이 숫자가 아님 → %d 으로 보정", tag, value, low)
        return str(low)
    fixed = max(low, min(high, number))
    if fixed != number:
        logger.warning("XML %s 값 %d 이 유효 범위(%d~%d) 밖 → %d 으로 보정", tag, number, low, high, fixed)
    return str(fixed)


def build_xml(output_path: str, **overrides):

    def _v(key, attr):
        return overrides.get(key, getattr(config, attr))

    def _b(value) -> str:
        return "true" if value else "false"

    target_model = str(overrides.get("target_model", "") or "").lower()
    is_pro = target_model == "pro"
    root_attrs = {}
    if is_pro:
        root_attrs = {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
        }
    root = ET.Element("GTOPTION", root_attrs)

    ink = int(_v("ink", "INK"))
    common_elements = [
        ("szFileName", ""),
        ("uiCopies", str(_v("copies", "COPIES"))),
        ("byPlatenSize", str(_v("platen_size", "PLATEN_SIZE"))),
        ("byInk", str(_v("ink", "INK"))),
        ("byResolution", str(_v("resolution", "RESOLUTION"))),
    ]

    pro_elements = list(common_elements)
    if ink == 0:
        pro_elements.extend([
            ("byInkVolume", str(_v("ink_volume", "INK_VOLUME"))),
            ("byDoublePrint", str(_v("double_print", "DOUBLE_PRINT"))),
            ("bMultiple", _b(_v("multiple", "MULTIPLE"))),
        ])
    elif ink == 1:
        pro_elements.extend([
            ("byHighlight", str(_v("highlight", "HIGHLIGHT"))),
            ("byMask", str(_v("mask", "MASK"))),
            ("bTransColor", _b(_v("trans_color", "TRANS_COLOR"))),
            ("colorTrans", str(_v("color_trans", "COLOR_TRANS"))),
            ("byTolerance", str(_v("tolerance", "TOLERANCE"))),
        ])
    elif ink == 2:
        pro_elements.extend([
            ("bEcoMode", _b(_v("eco_mode", "ECO_MODE"))),
            ("byHighlight", str(_v("highlight", "HIGHLIGHT"))),
            ("byMask", str(_v("mask", "MASK"))),
            ("bMaterialBlack", _b(_v("material_black", "MATERIAL_BLACK"))),
            ("bMultiple", _b(_v("multiple", "MULTIPLE"))),
            ("bTransColor", _b(_v("trans_color", "TRANS_COLOR"))),
            ("colorTrans", str(_v("color_trans", "COLOR_TRANS"))),
            ("byTolerance", str(_v("tolerance", "TOLERANCE"))),
            ("byMinWhite", str(_v("min_white", "MIN_WHITE"))),
            ("byChoke", str(_v("choke", "CHOKE"))),
            ("bPause", _b(_v("pause", "PAUSE"))),
        ])

    pro_elements.extend([
        ("bySaturation", str(_v("saturation", "SATURATION"))),
        ("byBrightness", str(_v("brightness", "BRIGHTNESS"))),
        ("byContrast", str(_v("contrast", "CONTRAST"))),
        ("iCyanBalance", str(_v("cyan_balance", "CYAN_BALANCE"))),
        ("iMagentaBalance", str(_v("magenta_balance", "MAGENTA_BALANCE"))),
        ("iYellowBalance", str(_v("yellow_balance", "YELLOW_BALANCE"))),
        ("iBlackBalance", str(_v("black_balance", "BLACK_BALANCE"))),
        ("bUniPrint", _b(_v("uni_print", "UNI_PRINT"))),
    ])

    elements = [
        ("szFileName", ""),
        ("uiCopies", str(_v("copies", "COPIES"))),
        ("byPlatenSize", str(_v("platen_size", "PLATEN_SIZE"))),
        ("byInk", str(_v("ink", "INK"))),
        ("bEcoMode", _b(_v("eco_mode", "ECO_MODE"))),
        ("byResolution", str(_v("resolution", "RESOLUTION"))),
        ("byHighlight", str(_v("highlight", "HIGHLIGHT"))),
        ("byMask", str(_v("mask", "MASK"))),
        ("byInkVolume", str(_v("ink_volume", "INK_VOLUME"))),
        ("byDoublePrint", str(_v("double_print", "DOUBLE_PRINT"))),
        ("bMaterialBlack", _b(_v("material_black", "MATERIAL_BLACK"))),
        ("bMultiple", _b(_v("multiple", "MULTIPLE"))),
        ("bTransColor", _b(_v("trans_color", "TRANS_COLOR"))),
        ("colorTrans", str(_v("color_trans", "COLOR_TRANS"))),
        ("byTolerance", str(_v("tolerance", "TOLERANCE"))),
        ("byMinWhite", str(_v("min_white", "MIN_WHITE"))),
        ("byChoke", str(_v("choke", "CHOKE"))),
        ("bPause", _b(_v("pause", "PAUSE"))),
        ("bySaturation", str(_v("saturation", "SATURATION"))),
        ("byBrightness", str(_v("brightness", "BRIGHTNESS"))),
        ("byContrast", str(_v("contrast", "CONTRAST"))),
        ("iCyanBalance", str(_v("cyan_balance", "CYAN_BALANCE"))),
        ("iMagentaBalance", str(_v("magenta_balance", "MAGENTA_BALANCE"))),
        ("iYellowBalance", str(_v("yellow_balance", "YELLOW_BALANCE"))),
        ("iBlackBalance", str(_v("black_balance", "BLACK_BALANCE"))),
        ("bUniPrint", _b(_v("uni_print", "UNI_PRINT"))),
    ]

    if is_pro:
        elements = pro_elements

    if not is_pro and overrides.get("include_machine_mode", True):
        elements.insert(2, ("byMachineMode", str(_v("machine_mode", "MACHINE_MODE"))))

    for tag, value in elements:
        el = ET.SubElement(root, tag)
        el.text = _clamped(tag, value)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
