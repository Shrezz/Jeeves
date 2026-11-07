import { useEffect } from 'react';
import { ClerkProvider, SignIn, SignUp, Show, useClerk, useUser } from '@clerk/react';
import { publishableKeyFromHost } from '@clerk/react/internal';
import { shadcn } from '@clerk/themes';
import { Switch, Route, Redirect, Link, useLocation, Router as WouterRouter } from 'wouter';
import { LogOut } from 'lucide-react';
import AccountDataBoundary from '@/components/account-data-boundary';
import { Mark } from '@/components/cw';
import { WorkspaceBrand, WorkspaceNav } from '@/components/workspace-nav';
import { UploadScreen, type ScreenId } from '@/pages/screens-a';
import DashboardScreen from '@/pages/dashboard';
import AccountPage from '@/pages/account';
import Landing from '@/pages/landing';
import NotFound from '@/pages/not-found';
import { ChatScreen, ClaimChooserScreen, ReviewScreen } from '@/pages/screens-b';

const clerkPubKey = publishableKeyFromHost(
  window.location.hostname,
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
);

const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL;

const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");

function stripBase(path: string): string {
  return basePath && path.startsWith(basePath)
    ? path.slice(basePath.length) || "/"
    : path;
}

function safeDecodePathPart(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

if (!clerkPubKey) {
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY in .env file');
}

const ink = 'hsl(192 30% 12%)';
const clerkAppearance = {
  theme: shadcn,
  cssLayerName: "clerk",
  options: {
    logoPlacement: "inside" as const,
    logoLinkUrl: basePath || "/",
    logoImageUrl: `${window.location.origin}${basePath}/logo.svg`,
  },
  variables: {
    colorPrimary: 'hsl(178 64% 27%)',
    colorForeground: ink,
    colorMutedForeground: 'hsl(192 12% 36%)',
    colorDanger: 'hsl(4 66% 44%)',
    colorBackground: 'hsl(40 40% 99%)',
    colorInput: 'hsl(40 40% 99%)',
    colorInputForeground: ink,
    colorNeutral: ink,
    fontFamily: "'Plus Jakarta Sans', sans-serif",
    borderRadius: '0.6rem',
  },
  elements: {
    rootBox: "w-full flex justify-center",
    // This MVP's visible auth flow is email-based; social login is deferred.
    socialButtons: { display: 'none' },
    dividerRow: { display: 'none' },
    cardBox: "bg-[hsl(40_40%_99%)] border border-[hsl(180_14%_86%)] rounded-2xl w-[440px] max-w-full overflow-hidden shadow-[0_18px_40px_-24px_hsl(192_30%_12%/0.35)]",
    card: "!shadow-none !border-0 !bg-transparent !rounded-none",
    footer: "!shadow-none !border-0 !bg-transparent !rounded-none",
    headerTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: '1.75rem', fontWeight: 600, color: ink, letterSpacing: '-0.015em' },
    headerSubtitle: "text-[hsl(192_12%_36%)]",
    socialButtonsBlockButtonText: "text-[hsl(192_30%_12%)] font-semibold",
    formFieldLabel: "text-[hsl(192_30%_12%)] font-semibold",
    footerActionLink: "text-[hsl(178_64%_27%)] font-semibold",
    footerActionText: "text-[hsl(192_12%_36%)]",
    dividerText: "text-[hsl(192_12%_36%)]",
    identityPreviewEditButton: "text-[hsl(178_64%_27%)]",
    formFieldSuccessText: "text-[hsl(178_64%_24%)]",
    alertText: "text-[hsl(4_66%_34%)]",
    logoBox: "justify-center h-11",
    logoImage: "h-11 w-11",
    socialButtonsBlockButton: "border border-[hsl(180_12%_76%)] bg-[hsl(40_40%_99%)]",
    formButtonPrimary: "bg-[hsl(178_64%_27%)] text-[hsl(40_40%_98%)] font-semibold",
    formFieldInput: "border border-[hsl(180_12%_76%)] bg-[hsl(40_40%_99%)] text-[hsl(192_30%_12%)]",
    footerAction: "bg-[hsl(40_20%_95%)] border-t border-[hsl(180_14%_86%)]",
    dividerLine: "bg-[hsl(180_14%_86%)]",
    alert: "border border-[hsl(4_66%_80%)] bg-[hsl(4_70%_97%)]",
    otpCodeFieldInput: "border border-[hsl(180_12%_76%)] text-[hsl(192_30%_12%)]",
    formFieldRow: "gap-3",
    main: "gap-5",
  },
};

function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[100dvh] flex-col bg-background">
      <header className="px-6 py-4"><Link href="/" className="inline-flex items-center gap-2" data-testid="link-home"><Mark className="h-7 w-7" /><span className="font-bold tracking-tight">Jeeves</span></Link></header>
      <div className="cw-enter flex flex-1 items-center justify-center px-4 pb-16">{children}</div>
    </div>
  );
}

function SignInPage() {
  useEffect(() => { document.title = 'Sign in — Jeeves'; }, []);
  return (
    <AuthShell>
      <SignIn routing="path" path={`${basePath}/sign-in`} signUpUrl={`${basePath}/sign-up`} fallbackRedirectUrl={`${basePath}/workspace/dashboard`} />
    </AuthShell>
  );
}

function SignUpPage() {
  useEffect(() => { document.title = 'Create account — Jeeves'; }, []);
  return (
    <AuthShell>
      <SignUp routing="path" path={`${basePath}/sign-up`} signInUrl={`${basePath}/sign-in`} forceRedirectUrl={`${basePath}/workspace/upload`} />
    </AuthShell>
  );
}

function Workspace() {
  const [location, setLocation] = useLocation();
  const path = stripBase(location).replace(/\/$/, '') || '/';
  const isUploadPage = path === '/workspace/upload' || path === '/workspace/upload/failed' || /^\/workspace\/upload\/success\/[^/]+$/.test(path);
  const successMatch = path.match(/^\/workspace\/upload\/success\/([^/]+)$/);
  const uploadOutcome = successMatch ? 'success' : path === '/workspace/upload/failed' ? 'failed' : 'form';
  const policyId = successMatch ? safeDecodePathPart(successMatch[1]) : undefined;
  const claimMatch = path.match(/^\/workspace\/claim\/([^/]+)$/);
  const claimId = claimMatch ? safeDecodePathPart(claimMatch[1]) : undefined;
  const validPath = path === '/workspace/account' || path === '/workspace/upload' || path === '/workspace/dashboard' || path === '/workspace/review' || path === '/workspace/status' || path === '/workspace/claim' || path === '/workspace/chat' || !!claimId || path === '/workspace/upload/failed' || !!successMatch;
  useEffect(() => {
    if (path === '/workspace/chat' || path === '/workspace/status') setLocation('/workspace/claim', { replace: true });
    else if (path === '/workspace' || !validPath) setLocation('/workspace/dashboard', { replace: true });
  }, [path, validPath, setLocation]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [path]);
  const go = (s: ScreenId) => {
    setLocation(s === 'dashboard' ? '/workspace/dashboard' : '/workspace/upload');
    window.scrollTo({ top: 0 });
  };
  const { user } = useUser();
  const { signOut } = useClerk();
  useEffect(() => {
    if (!isUploadPage || uploadOutcome === 'success') return;
    if (uploadOutcome === 'failed') document.title = 'Upload Failed — Jeeves';
    else document.title = 'Upload Policy — Jeeves';
  }, [isUploadPage, uploadOutcome]);
  const name = user?.fullName || user?.firstName || user?.primaryEmailAddress?.emailAddress || 'Your account';
  const initials = ((user?.firstName?.[0] ?? '') + (user?.lastName?.[0] ?? '')).toUpperCase() || name[0]?.toUpperCase() || '?';
  return (
    <div className="min-h-[100dvh]">
      <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <WorkspaceBrand />
          <span className="ml-auto flex min-w-0 items-center gap-3 text-sm text-muted-foreground">
            <span className="flex items-center gap-2">
              {user?.imageUrl && user.hasImage
                ? <img src={user.imageUrl} alt="" className="h-7 w-7 rounded-full object-cover" />
                : <span className="grid h-7 w-7 place-items-center rounded-full bg-secondary text-xs font-bold text-secondary-foreground" aria-hidden>{initials}</span>}
              <span data-testid="text-user-name" className="max-w-[12rem] truncate font-medium text-foreground">{name}</span>
            </span>
            <button type="button" data-testid="button-header-signout" onClick={() => signOut({ redirectUrl: basePath || "/" })} className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold transition-colors hover:bg-card hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              <LogOut className="h-3.5 w-3.5" aria-hidden /> Sign out
            </button>
          </span>
        </div>
        <WorkspaceNav path={path} />
      </header>
      <main className="cw-enter">
        <div hidden={!isUploadPage}>
          <UploadScreen
            go={go}
            outcome={uploadOutcome}
            policyId={policyId}
            onRoute={(nextPath) => setLocation(nextPath)}
          />
        </div>
        {path === '/workspace/dashboard' && <DashboardScreen go={go} />}
        {path === '/workspace/claim' && <ClaimChooserScreen />}
        {claimId && <ChatScreen key={`${user?.id}:${claimId}`} claimId={claimId} />}
        {path === '/workspace/account' && <AccountPage />}
        {path === '/workspace/review' && <ReviewScreen />}
      </main>
    </div>
  );
}

function AuthLoading() {
  return (
    <div className="min-h-[100dvh]" aria-busy="true" aria-label="Loading your session">
      <div className="flex items-center gap-3 border-b px-6 py-3"><Mark className="h-7 w-7" /><div className="h-4 w-24 animate-pulse rounded bg-muted" /><div className="ml-auto h-7 w-32 animate-pulse rounded-full bg-muted" /></div>
      <div className="mx-auto max-w-6xl space-y-4 p-6 sm:p-10">
        <div className="h-10 w-72 animate-pulse rounded-lg bg-muted" />
        {[0, 1, 2].map((i) => <div key={i} className="h-28 animate-pulse rounded-2xl bg-muted" />)}
      </div>
    </div>
  );
}

function HomeRedirect() {
  return (
    <>
      <Show when="signed-in">
        <Redirect to="/workspace/dashboard" />
      </Show>
      <Show when="signed-out">
        <Landing />
      </Show>
    </>
  );
}

function WorkspaceRoute() {
  const { isLoaded } = useUser();
  if (!isLoaded) return <AuthLoading />;
  return (
    <>
      <Show when="signed-in">
        <Workspace />
      </Show>
      <Show when="signed-out">
        <Redirect to="/" />
      </Show>
    </>
  );
}

function ClerkProviderWithRoutes() {
  const [, setLocation] = useLocation();

  return (
    <ClerkProvider
      publishableKey={clerkPubKey}
      proxyUrl={clerkProxyUrl}
      appearance={clerkAppearance}
      signInUrl={`${basePath}/sign-in`}
      signUpUrl={`${basePath}/sign-up`}
      signInFallbackRedirectUrl={`${basePath}/workspace/dashboard`}
      signUpForceRedirectUrl={`${basePath}/workspace/upload`}
      afterSignOutUrl={basePath || "/"}
      localization={{
        signIn: {
          start: {
            title: "Welcome back",
            subtitle: "Sign in to your Jeeves workspace",
          },
        },
        signUp: {
          start: {
            title: "Create your account",
            subtitle: "Keep your policy and claim paperwork in one place",
          },
        },
      }}
      routerPush={(to) => setLocation(stripBase(to))}
      routerReplace={(to) => setLocation(stripBase(to), { replace: true })}
    >
      <AccountDataBoundary>
        <Switch>
          <Route path="/" component={HomeRedirect} />
          <Route path="/sign-in/*?" component={SignInPage} />
          <Route path="/sign-up/*?" component={SignUpPage} />
          <Route path="/workspace/*?" component={WorkspaceRoute} />
          <Route component={NotFound} />
        </Switch>
      </AccountDataBoundary>
    </ClerkProvider>
  );
}

function App() {
  return (
    <WouterRouter base={basePath}>
      <ClerkProviderWithRoutes />
    </WouterRouter>
  );
}

export default App;
