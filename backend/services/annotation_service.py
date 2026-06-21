import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class AnnotationService:
    """Dibuja bounding boxes sobre imágenes y genera JPG anotado con OpenCV."""

    # Colores en BGR (OpenCV). Agregar clases según el modelo entrenado.
    COLORES_BGR: dict[str, tuple[int, int, int]] = {
        "planta": (34, 197, 94),  # verde
        "maleza": (68, 68, 239),  # rojo
        "faltante": (8, 179, 234),  # amarillo
        "default": (34, 197, 94),
    }
    COLOR_TEXTO_BGR: tuple[int, int, int] = (20, 83, 20)

    @staticmethod
    def generar_imagen_anotada(
        imagen_path: str,
        detecciones: list[dict],
        min_confidence: float = 0.5,
    ) -> bytes:
        """
        Dibuja bounding boxes sobre la imagen original y devuelve JPG en bytes.

        Args:
            imagen_path:    Path absoluto al archivo (JPG/PNG/TIFF 8 o 16 bit).
            detecciones:    Lista de dicts con keys:
                            confianza (float), x_min, y_min, x_max, y_max (float),
                            clase (str).
            min_confidence: Umbral mínimo; detecciones por debajo se omiten.

        Returns:
            bytes: JPG anotado listo para HttpResponse.

        Raises:
            FileNotFoundError: Si imagen_path no existe en disco.
            ValueError:        Si OpenCV ni PIL pueden abrir el archivo.
        """
        path = Path(imagen_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {imagen_path}")

        # Intentar leer con OpenCV (falla en TIFF 16-bit y algunos formatos)
        img = cv2.imread(str(path))

        # Fallback PIL para TIFF 16-bit o formatos no soportados por OpenCV
        if img is None:
            try:
                from PIL import Image as PILImage

                pil = PILImage.open(str(path)).convert("RGB")
                img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            except Exception as e:
                raise ValueError(f"No se puede leer la imagen: {e}")

        if img is None:
            raise ValueError(f"OpenCV y PIL no pudieron abrir: {imagen_path}")

        alto, ancho = img.shape[:2]

        # Escalar grosor y fuente según resolución de la imagen
        grosor = max(1, ancho // 400)
        fs = max(0.35, ancho / 2000)

        filtradas = [d for d in detecciones if d["confianza"] >= min_confidence]

        for det in filtradas:
            x1 = max(0, min(int(det["x_min"]), ancho - 1))
            y1 = max(0, min(int(det["y_min"]), alto - 1))
            x2 = max(0, min(int(det["x_max"]), ancho - 1))
            y2 = max(0, min(int(det["y_max"]), alto - 1))

            if x2 <= x1 or y2 <= y1:
                continue

            clase = str(det.get("clase", "planta")).lower()
            color = AnnotationService.COLORES_BGR.get(
                clase, AnnotationService.COLORES_BGR["default"]
            )

            # Bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), color, grosor)

            # Etiqueta: "clase XX%"
            label = f"{clase} {det['confianza']:.0%}"
            (tw, th), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, fs, 1
            )

            # Fondo de etiqueta (arriba del box; abajo si no hay espacio)
            ly = y1 - 4 if y1 - th - 8 >= 0 else y2 + th + 8
            cv2.rectangle(
                img,
                (x1, ly - th - 4),
                (x1 + tw + 8, ly + 2),
                color,
                cv2.FILLED,
            )
            cv2.putText(
                img,
                label,
                (x1 + 4, ly),
                cv2.FONT_HERSHEY_SIMPLEX,
                fs,
                AnnotationService.COLOR_TEXTO_BGR,
                1,
                cv2.LINE_AA,
            )

        # Watermark de conteo en esquina inferior izquierda
        wm = f"{len(filtradas)} detecciones"
        (ww, wh), _ = cv2.getTextSize(wm, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(
            img,
            (6, alto - wh - 12),
            (ww + 18, alto - 4),
            (0, 0, 0),
            cv2.FILLED,
        )
        cv2.putText(
            img,
            wm,
            (12, alto - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (209, 250, 229),
            1,
            cv2.LINE_AA,
        )

        ok, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise ValueError("No se pudo codificar el JPG anotado.")
        return buffer.tobytes()
