import { useState } from 'react';
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { MessageCircle, Bug } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";

export function FeedbackDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [type, setType] = useState<'feedback' | 'bug'>('feedback');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { toast } = useToast();

  const handleSubmit = async () => {
    try {
      setIsSubmitting(true);
      await apiRequest("POST", "/api/feedback", {
        type,
        message: feedback
      });

      toast({
        title: "Thank you for your feedback!",
        description: "We appreciate your input and will review it shortly.",
      });

      setFeedback('');
      setIsOpen(false);
    } catch (error) {
      toast({
        title: "Failed to submit feedback",
        description: "Please try again later.",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button
          id="feedback-button"
          variant="outline"
          size="icon"
          className="fixed bottom-4 right-4 h-12 w-12 rounded-full shadow-lg hover:shadow-xl transition-all"
        >
          <MessageCircle className="h-6 w-6" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send Feedback</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-4">
          <div className="flex gap-4">
            <Button
              variant={type === 'feedback' ? 'default' : 'outline'}
              className="flex-1"
              onClick={() => setType('feedback')}
            >
              <MessageCircle className="h-4 w-4 mr-2" />
              Feedback
            </Button>
            <Button
              variant={type === 'bug' ? 'default' : 'outline'}
              className="flex-1"
              onClick={() => setType('bug')}
            >
              <Bug className="h-4 w-4 mr-2" />
              Report Bug
            </Button>
          </div>
          <Textarea
            placeholder={type === 'feedback' ? 
              "Share your thoughts about the platform..." : 
              "Describe the issue you're experiencing..."
            }
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            className="min-h-[100px]"
          />
          <Button 
            className="w-full"
            onClick={handleSubmit}
            disabled={isSubmitting || !feedback.trim()}
          >
            Submit
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}