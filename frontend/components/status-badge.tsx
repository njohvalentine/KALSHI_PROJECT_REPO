import { Badge } from "@/components/ui/badge";
import type { RunSummary } from "@/lib/types";

const label: Record<RunSummary["status"], string> = {
  queued: "Queued",
  running: "Researching",
  done: "Done",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: RunSummary["status"] }) {
  const style =
    status === "done"
      ? "bg-good-soft text-good"
      : status === "failed"
        ? "bg-destructive/10 text-destructive"
        : "bg-warn-soft text-warn";
  return <Badge className={`${style} border-transparent`}>{label[status]}</Badge>;
}
