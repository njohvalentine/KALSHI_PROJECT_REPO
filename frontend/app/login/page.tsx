import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-(--gutter) py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight">Forecast desk</h1>
          <p className="mt-2 text-muted-foreground">AI research for Kalshi sports markets</p>
        </div>
        <div className="rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="text-xl font-semibold tracking-tight">Sign in</h2>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">Use the account your administrator gave you.</p>
          <LoginForm />
        </div>
        <p className="mt-6 text-center text-sm text-muted-foreground">Paper trading only: nothing is ordered on Kalshi.</p>
      </div>
    </main>
  );
}
