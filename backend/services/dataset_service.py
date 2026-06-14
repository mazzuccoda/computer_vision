import logging
import random
import shutil
import zipfile
from pathlib import Path

import yaml
from django.conf import settings

logger = logging.getLogger(__name__)
IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# TODO FASE 2: activar datumaro para CVAT XML y COCO
# TODO FASE 3: augmentations configurables (mosaic, flipud, degrees)


class DatasetValidationError(Exception):
    pass


class DatasetService:
    @staticmethod
    def validar_y_preparar(dataset) -> dict:
        """
        Descomprime el .zip, detecta formato, valida y convierte a YOLO.
        Returns: {data_yaml_path, num_imagenes, clases, reporte}
        Raises: DatasetValidationError con mensaje descriptivo.
        """
        zip_path = Path(dataset.archivo.path)
        work_dir = Path(settings.MEDIA_ROOT) / "datasets_proc" / str(dataset.id)
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(work_dir)
        except zipfile.BadZipFile:
            raise DatasetValidationError("El archivo no es un .zip válido.")

        fmt = dataset.formato
        if fmt == "yolo":
            return DatasetService._procesar_yolo(work_dir)
        elif fmt in ("cvat_xml", "coco"):
            return DatasetService._procesar_con_datumaro(work_dir, fmt)
        raise DatasetValidationError(f"Formato no soportado: {fmt}")

    @staticmethod
    def _procesar_yolo(work_dir: Path) -> dict:
        all_images = [
            p for p in work_dir.rglob("*") if p.suffix.lower() in IMG_EXTS
        ]
        if len(all_images) < 5:
            raise DatasetValidationError(
                f"Dataset muy pequeño: {len(all_images)} imágenes. Mínimo 5."
            )

        all_labels = [
            label
            for label in work_dir.rglob("*.txt")
            if label.name != "classes.txt"
        ]
        if not all_labels:
            raise DatasetValidationError(
                "No se encontraron archivos .txt de anotaciones YOLO."
            )

        clases = DatasetService._detectar_clases(work_dir, all_labels)

        if not (work_dir / "images" / "train").exists():
            DatasetService._crear_split(work_dir, all_images)

        data_yaml_path = work_dir / "data.yaml"
        with open(data_yaml_path, "w") as f:
            yaml.dump(
                {
                    "path": str(work_dir),
                    "train": "images/train",
                    "val": "images/val",
                    "nc": len(clases),
                    "names": clases,
                },
                f,
                allow_unicode=True,
            )

        distribucion = DatasetService._contar_distribucion(all_labels, clases)
        warnings = []
        if len(all_images) < 20:
            warnings.append(f"Dataset pequeño ({len(all_images)} imgs).")
        for cls, cnt in distribucion.items():
            if cnt < 10:
                warnings.append(
                    f"Clase '{cls}' tiene pocas anotaciones ({cnt})."
                )

        return {
            "data_yaml_path": str(data_yaml_path),
            "num_imagenes": len(all_images),
            "clases": clases,
            "reporte": {
                "total_imagenes": len(all_images),
                "total_anotaciones": sum(distribucion.values()),
                "distribucion_por_clase": distribucion,
                "warnings": warnings,
            },
        }

    @staticmethod
    def _procesar_con_datumaro(work_dir: Path, fmt: str) -> dict:
        try:
            import datumaro as dm
        except ImportError:
            raise DatasetValidationError(
                "Soporte de CVAT XML / COCO no disponible: instalar datumaro "
                "(pip install datumaro). El formato YOLO sí está soportado."
            )
        dm_fmt = "cvat" if fmt == "cvat_xml" else "coco_instances"
        output = work_dir / "converted"
        dm.Dataset.import_from(str(work_dir), format=dm_fmt).export(
            str(output), format="yolo"
        )
        return DatasetService._procesar_yolo(output)

    @staticmethod
    def _detectar_clases(work_dir: Path, label_files: list) -> list:
        classes_txt = work_dir / "classes.txt"
        if classes_txt.exists():
            return [
                line.strip()
                for line in classes_txt.read_text().splitlines()
                if line.strip()
            ]
        max_cls = 0
        for lf in label_files[:50]:
            try:
                for line in lf.read_text().splitlines():
                    if line.strip():
                        max_cls = max(max_cls, int(line.split()[0]))
            except Exception:
                pass
        return [f"clase_{i}" for i in range(max_cls + 1)]

    @staticmethod
    def _crear_split(work_dir: Path, images: list, ratio: float = 0.8):
        random.shuffle(images)
        n = int(len(images) * ratio)
        # Garantizar al menos 1 imagen en validación.
        if n >= len(images):
            n = len(images) - 1
        for subset, imgs in [("train", images[:n]), ("val", images[n:])]:
            (work_dir / "images" / subset).mkdir(parents=True, exist_ok=True)
            (work_dir / "labels" / subset).mkdir(parents=True, exist_ok=True)
            for img in imgs:
                shutil.copy2(img, work_dir / "images" / subset / img.name)
                lbl = img.with_suffix(".txt")
                if not lbl.exists():
                    lbl = img.parent.parent / "labels" / lbl.name
                if lbl.exists():
                    shutil.copy2(
                        lbl, work_dir / "labels" / subset / lbl.name
                    )

    @staticmethod
    def _contar_distribucion(label_files: list, clases: list) -> dict:
        dist = {c: 0 for c in clases}
        for lf in label_files:
            try:
                for line in lf.read_text().splitlines():
                    if line.strip():
                        idx = int(line.split()[0])
                        if idx < len(clases):
                            dist[clases[idx]] += 1
            except Exception:
                pass
        return dist
