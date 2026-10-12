import { redirect } from "next/navigation";

// The markets list became the games list. Old links keep working.
export default function MarketsPage() {
  redirect("/games");
}
