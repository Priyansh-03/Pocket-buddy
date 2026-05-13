import * as React from "react";

import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        "flex min-h-[72px] w-full rounded-xl border border-transparent bg-black/5 px-4 py-3 text-sm text-[#e8eef5]",
        "placeholder:text-[#8b98a8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40",
        "disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white/5 dark:placeholder:text-white/50",
        className,
      )}
      ref={ref}
      {...props}
    />
  );
});
Textarea.displayName = "Textarea";

export { Textarea };
