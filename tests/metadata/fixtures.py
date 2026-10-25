"""OCR glyph fixtures shared by metadata tests."""

def line(text, x=.5, y=.5):
    return {"text": text, "confidence": .99, "box": [x - .02, y - .01, .04, .02]}


def glyph(text, x, y, width=.05, height=.025, confidence=1):
    return {"text": text, "box": [x, y, width, height], "confidence": confidence}
