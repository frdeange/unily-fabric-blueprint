import { useSemanticModelQuery } from '@/hooks/use-semantic-model-query';
import { parseAdoption } from '@/lib/adoption';
import { adoptionQueries, USAGE_CONNECTION } from '@/queries/adoption';

export function useAdoption() {
  const totals = useSemanticModelQuery({
    connection: USAGE_CONNECTION,
    query: adoptionQueries.totals,
  });
  const features = useSemanticModelQuery({
    connection: USAGE_CONNECTION,
    query: adoptionQueries.features,
  });
  const refresh = () => Promise.all([totals.refetch(), features.refetch()]);

  if (
    totals.error ||
    features.error ||
    totals.data?.status === 'error' ||
    features.data?.status === 'error'
  ) {
    return {
      status: 'error' as const,
      message:
        'Live analytics could not be loaded. Verify your model Read/Build access and try again.',
      refresh,
    };
  }
  if (
    totals.isLoading ||
    features.isLoading ||
    !totals.data ||
    !features.data
  ) {
    return { status: 'loading' as const, refresh };
  }
  try {
    return {
      status: 'ready' as const,
      totals: parseAdoption(totals.data.table),
      features: parseAdoption(features.data.table, true),
      refresh,
    };
  } catch (error) {
    return {
      status: 'error' as const,
      message:
        error instanceof Error
          ? error.message
          : 'Unexpected model response. Contact the app maintainer.',
      refresh,
    };
  }
}
