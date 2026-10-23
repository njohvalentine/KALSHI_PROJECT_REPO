import { Badge } from "@/components/ui/badge";
import type { ConfidenceLevel } from "@/lib/types";

const STYLE: Record<ConfidenceLevel, string> = {
  high: "bg-good-soft text-good",
  medium: "bg-secondary text-secondary-foreground",
  low: "bg-warn-soft text-warn",
};

/** The confidence level with its reasons. It says how consistent the three forecasts and the evidence are, not how likely the forecast is to be right. */
export function Confidence({ level, reasons }: { level: ConfidenceLevel; reasons: string[] }) {
  return (
    <div>
      <Badge className={STYLE[level]}>{level[0].toUpperCase() + level.slice(1)} confidence</Badge>
      <div className="mt-1 text-sm text-muted-foreground">{reasons.join("; ")}.</div>
    </div>
  );
}
