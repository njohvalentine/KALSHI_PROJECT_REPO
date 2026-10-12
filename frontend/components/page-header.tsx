export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-7 max-w-[70ch]">
      <h1 className="mb-2 text-3xl font-bold leading-tight tracking-tight">{title}</h1>
      {description ? <p className="text-muted-foreground">{description}</p> : null}
    </div>
  );
}
