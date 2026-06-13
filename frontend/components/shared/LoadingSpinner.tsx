import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export function LoadingSpinner({ className }: { className?: string }) {
  return (
    <div className="flex w-full items-center justify-center py-10">
      <Loader2 className={cn("h-6 w-6 animate-spin text-primary", className)} />
    </div>
  );
}
