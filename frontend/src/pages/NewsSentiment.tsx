import { PageContainer } from "../components/layout";
import { NewsList } from "../components/news";

export function NewsSentiment() {
  return (
    <PageContainer
      title="Intelligence"
      subtitle="Latest news and social sentiment across tracked stocks"
    >
      <NewsList />
    </PageContainer>
  );
}