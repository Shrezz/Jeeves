import { QueryClient } from '@tanstack/react-query';

export function createAccountQueryClient() {
  return new QueryClient();
}
