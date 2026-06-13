"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
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
import { useCampos } from "@/hooks/useCampos";
import {
  useCreateModulo,
  useDeleteModulo,
  useModulos,
} from "@/hooks/useModulos";

const schema = z.object({
  campo: z.coerce.number().int().positive("Seleccioná un campo"),
  nombre: z.string().min(1, "El nombre es requerido"),
  descripcion: z.string().optional(),
});

type FormValues = z.input<typeof schema>;

function ModuloForm() {
  const [open, setOpen] = useState(false);
  const { data: campos } = useCampos();
  const createModulo = useCreateModulo();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { campo: undefined, nombre: "", descripcion: "" },
  });

  async function onSubmit(values: FormValues) {
    const payload = schema.parse(values);
    try {
      await createModulo.mutateAsync(payload);
      toast.success("Módulo creado");
      form.reset({ campo: undefined, nombre: "", descripcion: "" });
      setOpen(false);
    } catch {
      toast.error("No se pudo crear el módulo");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Nuevo módulo</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo módulo</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="campo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Campo</FormLabel>
                  <FormControl>
                    <select
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value)}
                    >
                      <option value="">Seleccioná un campo</option>
                      {campos?.results.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.nombre}
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
                    <Input placeholder="Módulo A" {...field} />
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
            <Button
              type="submit"
              className="w-full"
              disabled={createModulo.isPending}
            >
              Crear módulo
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export default function ModulosPage() {
  const { data, isLoading } = useModulos();
  const deleteModulo = useDeleteModulo();

  async function handleDelete(id: number, nombre: string) {
    if (!confirm(`¿Eliminar el módulo "${nombre}"?`)) return;
    try {
      await deleteModulo.mutateAsync(id);
      toast.success("Módulo eliminado");
    } catch {
      toast.error("No se pudo eliminar el módulo");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Módulos</h2>
          <p className="text-muted-foreground">
            Gestioná los módulos de cada campo.
          </p>
        </div>
        <ModuloForm />
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : data && data.results.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.results.map((m) => (
            <div
              key={m.id}
              className="flex items-start justify-between rounded-lg border bg-card p-4"
            >
              <div>
                <p className="font-medium">{m.nombre}</p>
                <p className="text-sm text-muted-foreground">
                  {m.campo_nombre}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {m.descripcion || "—"}
                </p>
              </div>
              <Button
                variant="outline"
                size="icon"
                onClick={() => handleDelete(m.id, m.nombre)}
                disabled={deleteModulo.isPending}
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">
          No hay módulos todavía. Creá el primero.
        </p>
      )}
    </div>
  );
}
