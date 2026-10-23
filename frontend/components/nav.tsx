"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const items = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/games", label: "Games" },
  { href: "/opportunities", label: "Opportunities" },
  { href: "/ranking", label: "Ranking" },
  { href: "/prediction", label: "Prediction" },
  { href: "/approval", label: "Approval" },
  { href: "/results", label: "Results" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-wrap gap-1">
      {items.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-lg px-2.5 py-2 font-medium text-muted-foreground hover:bg-muted hover:text-foreground",
              active && "bg-secondary text-primary hover:bg-secondary hover:text-primary",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
