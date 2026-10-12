import { cn } from "@/lib/utils";

/** The one content width. The header, every page and the login page all use this. */
export function PageContainer({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("mx-auto w-full max-w-(--content-width) px-(--gutter)", className)}
      data-page-container
      {...props}
    />
  );
}
