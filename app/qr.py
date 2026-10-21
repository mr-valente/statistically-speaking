"""QR codes for joining a session, rendered as SVG with no runtime dependencies beyond segno."""

import io

import segno

# Scanners want a quiet zone; three modules is plenty inside a white card.
_QUIET_ZONE = 3


def svg_document(url: str) -> str:
    """A standalone SVG (with XML declaration and namespace) encoding ``url``.

    Error level M survives a projector's blur and a phone's glare; the symbol
    carries its own white background so it scans on the dark theme.
    """
    qr = segno.make(url, error="m")
    out = io.BytesIO()
    qr.save(out, kind="svg", scale=1, border=_QUIET_ZONE, dark="#0f1117", light="#ffffff",
            omitsize=True, xmldecl=True, svgns=True, svgclass="qr", lineclass=None)
    return out.getvalue().decode()
