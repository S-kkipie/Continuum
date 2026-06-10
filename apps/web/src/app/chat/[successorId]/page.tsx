import { MentorChat } from "@/components/mentor-chat";

export default async function ChatPage({ params }: { params: Promise<{ successorId: string }> }) {
  const { successorId } = await params;
  return <MentorChat successorId={successorId} />;
}
