"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateCampo, useUpdateCampo } from "@/hooks/useCampos";
import { Campo } from "@/types";

const MapaPicker = dynamic(() => import("@/components/mapa/MapaPicker"), {
  ssr: false,
  loading: () => (
    <div className="h-[240px] animate-pulse rounded-lg bg-muted" />
  ),
});

const schema = z.object({
  nombre: z.string().min(1, "El nombre es requerido"),
  descripcion: z.string().optional(),
  ubicacion: z.string().optional(),
  latitud: z
    .union([z.coerce.number(), z.literal("")])
    .optional()
    .transform((v) => (v === "" || v === undefined ? null : v)),
  longitud: z
    .union([z.coerce.number(), z.literal("")])
    .optional()
    .transform((v) => (v === "" || v === undefined ? null : v)),
});

type FormValues = z.input<typeof schema>;

interface CampoFormProps {
  campo?: Campo;
  trigger?: React.ReactNode;
}

export function CampoForm({ campo, trigger }: CampoFormProps) {
  const [open, setOpen] = useState(false);
  const createCampo = useCreateCampo();
  const updateCampo = useUpdateCampo();
  const isEdit = Boolean(campo);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre: campo?.nombre ?? "",
      descripcion: campo?.descripcion ?? "",
      ubicacion: campo?.ubicacion ?? "",
      latitud: campo?.latitud ?? "",
      longitud: campo?.longitud ?? "",
    },
  });

  useEffect(() => {
    if (open && campo) {
      form.reset({
        nombre: campo.nombre,
        descripcion: campo.descripcion,
        ubicacion: campo.ubicacion,
        latitud: campo.latitud ?? "",
        longitud: campo.longitud ?? "",
      });
    }
  }, [open, campo, form]);

  async function onSubmit(values: FormValues) {
    const payload = schema.parse(values);
    try {
      if (isEdit && campo) {
        await updateCampo.mutateAsync({ id: campo.id, payload });
        toast.success("Campo actualizado");
      } else {
        await createCampo.mutateAsync(payload);
        toast.success("Campo creado");
        form.reset({
          nombre: "",
          descripcion: "",
          ubicacion: "",
          latitud: "",
          longitud: "",
        });
      }
      setOpen(false);
    } catch {
      toast.error("No se pudo guardar el campo");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? <Button>Nuevo campo</Button>}
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Editar campo" : "Nuevo campo"}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="nombre"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nombre</FormLabel>
                  <FormControl>
                    <Input placeholder="Campo Norte" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="descripcion"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Descripción</FormLabel>
                  <FormControl>
                    <Input placeholder="Opcional" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="ubicacion"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Ubicación</FormLabel>
                  <FormControl>
                    <Input placeholder="Mendoza, Argentina" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="space-y-1">
              <Label>Ubicación en el mapa</Label>
              <p className="text-xs text-muted-foreground">
                Hacé clic en el mapa para fijar las coordenadas.
              </p>
              <MapaPicker
                latitud={
                  form.watch("latitud") === "" ||
                  form.watch("latitud") === undefined
                    ? null
                    : Number(form.watch("latitud"))
                }
                longitud={
                  form.watch("longitud") === "" ||
                  form.watch("longitud") === undefined
                    ? null
                    : Number(form.watch("longitud"))
                }
                onPick={(lat, lon) => {
                  form.setValue("latitud", lat, { shouldValidate: true });
                  form.setValue("longitud", lon, { shouldValidate: true });
                }}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="latitud"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Latitud</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step="any"
                        placeholder="-32.89"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="longitud"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Longitud</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step="any"
                        placeholder="-68.84"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <Button
              type="submit"
              className="w-full"
              disabled={createCampo.isPending || updateCampo.isPending}
            >
              {isEdit ? "Guardar cambios" : "Crear campo"}
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
