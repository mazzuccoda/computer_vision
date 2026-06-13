"use client";

import { Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { useUploadImages } from "@/hooks/useVuelos";

const ACCEPTED = ".tiff,.tif,.jpg,.jpeg,.png";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ImageUploader({ vueloId }: { vueloId: number }) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadImages = useUploadImages();

  function handleSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleUpload() {
    if (files.length === 0) {
      toast.error("Seleccioná al menos una imagen");
      return;
    }
    setProgress(0);
    try {
      await uploadImages.mutateAsync({
        id: vueloId,
        files,
        onProgress: setProgress,
      });
      toast.success(`${files.length} imágenes subidas`);
      setFiles([]);
      setProgress(0);
      setOpen(false);
    } catch {
      toast.error("Error al subir las imágenes");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Upload className="mr-2 h-4 w-4" />
          Cargar imágenes
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cargar imágenes</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED}
            onChange={handleSelect}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-input p-8 text-sm text-muted-foreground transition-colors hover:border-primary"
          >
            <Upload className="h-8 w-8" />
            <span>Hacé clic para seleccionar imágenes</span>
            <span className="text-xs">TIFF, TIF, JPG, JPEG, PNG</span>
          </button>

          {files.length > 0 && (
            <ul className="max-h-48 space-y-1 overflow-y-auto">
              {files.map((file, i) => (
                <li
                  key={`${file.name}-${i}`}
                  className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                >
                  <span className="truncate">{file.name}</span>
                  <span className="flex items-center gap-2 text-muted-foreground">
                    {formatSize(file.size)}
                    <button type="button" onClick={() => removeFile(i)}>
                      <X className="h-4 w-4" />
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          {uploadImages.isPending && <Progress value={progress} />}

          <Button
            className="w-full"
            onClick={handleUpload}
            disabled={uploadImages.isPending || files.length === 0}
          >
            {uploadImages.isPending
              ? `Subiendo... ${progress}%`
              : `Subir ${files.length || ""} imágenes`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
