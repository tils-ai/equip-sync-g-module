"""가먼트 CLI용 인쇄 설정 XML 생성."""

import xml.etree.ElementTree as ET

import config


def build_xml(output_path: str, **overrides):
    """config.ini 기반 + 오버라이드로 인쇄 설정 XML 생성.

    각 XML 요소는 가먼트 CLI Command-line Tool 가이드 3-1-2 절 참조.
    GTXpro는 byInk 값별 유효 요소가 나뉘므로, pro 대상에서는 공식 예제와
    같은 조건부 요소만 출력한다.
    """

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

    # legacy(GTX-4)는 가이드 §3-1-2 정의 순서(byInk→bEcoMode→byResolution)를 그대로
    # 따른다. common_elements(byInk 뒤 byResolution)는 pro 전용 순서이므로 재사용하지 않는다.
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

    # GTXpro XML spec does not define byMachineMode. Keep it only for legacy
    # GTX-4 ARX4 generation, where the official guide requires the field.
    if not is_pro and overrides.get("include_machine_mode", True):
        elements.insert(2, ("byMachineMode", str(_v("machine_mode", "MACHINE_MODE"))))

    for tag, value in elements:
        el = ET.SubElement(root, tag)
        el.text = value

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
