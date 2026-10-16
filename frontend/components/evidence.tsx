import { Fold } from "@/components/fold";
import { Badge } from "@/components/ui/badge";
import { host } from "@/lib/format";
import { fetchLabel, isMarketFinding, VERDICT } from "@/lib/labels";
import type { Claim, ClaimCheck, Finding, PageInfo, Run, Verdict } from "@/lib/types";

const VERDICT_STYLE: Record<Verdict, string> = {
  supported: "bg-good-soft text-good",
  not_supported: "bg-destructive/10 text-destructive",
  could_not_check: "bg-warn-soft text-warn",
};

function ClaimItem({ claim, checks }: { claim: Claim; checks: ClaimCheck[] }) {
  return (
    <li className="border-b py-4 last:border-b-0">
      <p className="mb-1.5 font-medium">{claim.text}</p>
      {claim.kind === "uncited" ? <Badge className="bg-warn-soft text-warn">No source given</Badge> : null}
      {claim.kind === "none" ? <Badge variant="outline">Nothing found</Badge> : null}
      <ul className="grid gap-2">
        {claim.sources.map((s) => {
          const check = checks.find((c) => c.source_url === s.url);
          return (
            <li key={s.url} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              {check ? (
                <Badge className={VERDICT_STYLE[check.verdict]}>{VERDICT[check.verdict]}</Badge>
              ) : (
                <Badge className="bg-secondary text-secondary-foreground">Cited, not checked</Badge>
              )}
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-4">
                {s.title || host(s.url)} <span className="text-muted-foreground">({host(s.url)})</span>
              </a>
              {check ? <span className="basis-full">{check.reason}</span> : null}
            </li>
          );
        })}
      </ul>
    </li>
  );
}

function FindingBlock({ finding, index, checks }: { finding: Finding; index: number; checks: ClaimCheck[] }) {
  return (
    <section className="mb-6">
      <h3 className="mb-1 text-lg font-semibold tracking-tight">{isMarketFinding(finding) ? "Market prices found (not given to the forecasters)" : finding.angle}</h3>
      <p className="mb-1 text-sm text-muted-foreground">{finding.question}</p>
      <ul>
        {finding.claims.map((c, i) => (
          <ClaimItem key={i} claim={c} checks={checks.filter((k) => k.finding_index === index && k.claim_index === i)} />
        ))}
      </ul>
    </section>
  );
}

export function EvidenceSection({ run }: { run: Run }) {
  const findings = run.result?.findings ?? [];
  if (findings.length === 0) return null;
  const forecasted = findings.filter((f) => !isMarketFinding(f));
  const cited = forecasted.reduce((n, f) => n + f.claims.filter((c) => c.kind === "sourced").length, 0);
  const supported = run.prediction?.supported_claims;
  const checked = run.claim_checks.length > 0;

  return (
    <Fold
      id="evidence"
      title="The evidence"
      summary={checked && supported !== undefined ? `${supported} of ${cited} cited facts were supported by their page` : `${cited} cited facts`}
    >
      <p className="mb-4 text-sm text-muted-foreground">
        {checked && supported !== undefined
          ? `${supported} of ${cited} cited facts were supported by their page and went to the forecasters.`
          : "“Cited” means the search tool attached a source link to the line."}{" "}
        “Supported” means the page itself says it; “Could not check” means the page could not be read, does not say it, or the claim was worked
        out rather than stated. Only supported facts are used.
      </p>
      {findings.map((f, i) => (
        <FindingBlock key={f.angle} finding={f} index={i} checks={run.claim_checks} />
      ))}
    </Fold>
  );
}

export function PagesSection({ pages }: { pages: PageInfo[] }) {
  if (pages.length === 0 || pages.every((p) => p.fetch_status === "not_fetched")) return null;
  return (
    <Fold id="pages" title="Pages we tried to read" summary={`${pages.length} pages, ${pages.filter((p) => p.fetch_status === "ok").length} read`}>
      <ul className="grid gap-2 text-sm">
        {pages.map((p) => (
          <li key={p.url} className="flex flex-wrap justify-between gap-x-4 gap-y-0.5 border-b pb-2 last:border-b-0">
            <a href={p.url} target="_blank" rel="noopener noreferrer" className="min-w-0 break-words text-primary underline underline-offset-4">
              {p.title || host(p.url)} <span className="text-muted-foreground">({host(p.url)})</span>
            </a>
            <span className={p.fetch_status === "ok" ? "text-good" : "text-muted-foreground"}>{fetchLabel(p.fetch_status, p.fetch_detail)}</span>
          </li>
        ))}
      </ul>
    </Fold>
  );
}
