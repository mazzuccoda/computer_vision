"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
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
import { useModulos } from "@/hooks/useModulos";
import { useCreateVuelo } from "@/hooks/useVuelos";

const schema = z.object({
  modulo: z.coerce.number().int().positive("Seleccioná un módulo"),
  nombre: z.string().min(1, "El nombre es requerido"),
  fecha_vuelo: z.string().min(1, "La fecha es requerida"),
});

type FormValues = z.input<typeof schema>;

export function VueloForm() {
  const [open, setOpen] = useState(false);
  const { data: modulos } = useModulos();
  const createVuelo = useCreateVuelo();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      modulo: undefined,
      nombre: "",
      fecha_vuelo: new Date().toISOString().slice(0, 10),
    },
  });

  async function onSubmit(values: FormValues) {
    const payload = schema.parse(values);
    try {
      await createVuelo.mutateAsync(payload);
      toast.success("Vuelo creado");
      form.reset({
        modulo: undefined,
        nombre: "",
        fecha_vuelo: new Date().toISOString().slice(0, 10),
      });
      setOpen(false);
    } catch {
      toast.error("No se pudo crear el vuelo");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Nuevo vuelo</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo vuelo</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="modulo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Módulo</FormLabel>
                  <FormControl>
                    <select
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value)}
                    >
                      <option value="">Seleccioná un módulo</option>
                      {modulos?.results.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.nombre} ({m.campo_nombre})
                        </option>
                      ))}
                    </select>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="nombre"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nombre</FormLabel>
                  <FormControl>
                    <Input placeholder="Vuelo mañana" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="fecha_vuelo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Fecha del vuelo</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button
              type="submit"
              className="w-full"
              disabled={createVuelo.isPending}
            >
              Crear vuelo
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
