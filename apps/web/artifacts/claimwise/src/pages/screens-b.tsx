import { ClaimWorkspacePage } from './claim-workspace';
import ClaimChooserPage from './claim-chooser';
import ReviewPackagePage from './review-package';

export function ChatScreen({ claimId }: { claimId: string }) {
  return <ClaimWorkspacePage claimId={claimId} />;
}

export function ClaimChooserScreen() {
  return <ClaimChooserPage />;
}

export function ReviewScreen() {
  return <ReviewPackagePage />;
}
