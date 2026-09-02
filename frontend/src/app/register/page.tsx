import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Wordmark } from "@/components/molecules/wordmark";
import { LoginForm } from "@/features/auth/component/login-form";

export default function RegisterPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader className="flex flex-col items-center gap-1">
          <Wordmark />
          <p className="text-sm text-ink-muted">
            Indian legal research over primary sources.
          </p>
        </CardHeader>
        <CardContent>
          <LoginForm mode="signUp" />
        </CardContent>
      </Card>
    </main>
  );
}
