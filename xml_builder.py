"""GTX4CMD.exe용 인쇄 설정 XML 생성."""

import xml.etree.ElementTree as ET

import config


def build_xml(output_path: str, **overrides):
    """config.ini 기반 + 오버라이드로 인쇄 설정 XML 생성.

    각 XML 요소는 Brother GTX-4 Command-line Tool 가이드 3-1-2 절 참조.
    요소를 생략하면 GTX4CMD는 '0'으로 간주하므로, UI 값을 모두 명시적으로 출력한다.
    """

    def _v(key, attr):
        return overrides.get(key, getattr(config, attr))

    def _b(value) -> str:
        return "true" if value else "false"

    root = ET.Element("GTOPTION")

    elements = [
        ("szFileName", ""),
        ("uiCopies", str(_v("copies", "COPIES"))),
        ("byMachineMode", str(_v("machine_mode", "MACHINE_MODE"))),
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

    for tag, value in elements:
        el = ET.SubElement(root, tag)
        el.text = value

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
