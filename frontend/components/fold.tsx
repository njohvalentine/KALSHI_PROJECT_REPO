/** A section that is closed until a person opens it. The summary line says what is inside, so closed does not mean hidden.
 * It is a native <details> element: it works without scripts, with the keyboard and with screen readers. */
export function Fold({
  id,
  title,
  summary,
  defaultOpen = false,
  level = "h2",
  children,
}: {
  id?: string;
  title: string;
  summary?: React.ReactNode;
  defaultOpen?: boolean;
  level?: "h2" | "h3";
  children: React.ReactNode;
}) {
  const Heading = level;
  return (
    <details id={id} open={defaultOpen} className="group mb-4 rounded-xl border bg-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span>
          <Heading className="text-lg font-semibold tracking-tight">{title}</Heading>
          {summary ? <span className="block text-sm text-muted-foreground">{summary}</span> : null}
        </span>
        <span aria-hidden className="text-muted-foreground transition-transform group-open:rotate-180">
          ⌄
        </span>
      </summary>
      <div className="border-t px-4 py-4">{children}</div>
    </details>
  );
}
