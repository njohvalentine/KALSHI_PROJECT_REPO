export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6 max-w-[70ch]">
      <h1 className="mb-1 text-[1.75rem] font-bold leading-tight tracking-tight">{title}</h1>
      {description ? <p className="text-muted-foreground">{description}</p> : null}
    </div>
  );
}
