import { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { ShieldCheck, Layers, Cpu, Sparkles, AlertCircle } from 'lucide-react';
import { useVerification } from '../hooks/useVerification';
import { useImageVerification } from '../hooks/useImageVerification';
import { ClaimInput } from '../components/verify/ClaimInput';
import { ImageUpload } from '../components/verify/ImageUpload';
import { LoadingState } from '../components/verify/LoadingState';
import { ErrorState } from '../components/verify/ErrorState';
import { VerdictCard } from '../components/verify/VerdictCard';
import { ExplanationBlock } from '../components/verify/ExplanationBlock';
import { ConfidenceBreakdownPanel } from '../components/verify/ConfidenceBreakdownPanel';
import { AgreementSignalPanel } from '../components/verify/AgreementSignalPanel';
import { EvidenceList } from '../components/verify/EvidenceList';
import { ImageVerificationResult } from '../components/verify/ImageVerificationResult';

export const VerifyPage = () => {
  const location = useLocation();
  const initialClaim = location.state?.claim || '';
  
  // Track current claim and verification mode
  const [currentClaim, setCurrentClaim] = useState(initialClaim);
  const [activeTab, setActiveTab] = useState('text'); // 'text' or 'image'
  const resultRef = useRef(null);

  const {
    mutate: verifyClaim,
    isPending: isTextPending,
    isError: isTextError,
    isSuccess: isTextSuccess,
    data: textResult,
    error: textError,
    reset: resetText,
  } = useVerification();

  const {
    mutate: verifyImageFile,
    isPending: isImagePending,
    isError: isImageError,
    isSuccess: isImageSuccess,
    data: imageResult,
    error: imageError,
    reset: resetImage,
  } = useImageVerification();

  const handleTextVerifySubmit = (claimText) => {
    setCurrentClaim(claimText);
    resetText();
    verifyClaim(claimText);
  };

  const handleImageVerifySubmit = (file, claimText = null) => {
    resetImage();
    verifyImageFile({ file, claim: claimText });
  };

  const handleRetry = () => {
    if (activeTab === 'text' && currentClaim) {
      resetText();
      verifyClaim(currentClaim);
    }
  };

  // Auto-submit if navigated with a sample claim
  useEffect(() => {
    if (initialClaim && !isTextPending) {
      resetText();
      verifyClaim(initialClaim);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Accessibility polish: Scroll to results smoothly
  useEffect(() => {
    if ((textResult || imageResult) && !isTextPending && !isImagePending && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [textResult, imageResult, isTextPending, isImagePending]);

  const isTextLoading = isTextPending;
  const isImageLoading = isImagePending;

  // Extract structured properties with legacy fallback
  const textAssessment = textResult?.text_assessment;
  const displayClaim = textResult?.claim_details?.original || textResult?.claim || currentClaim;
  const displayVerdict = textAssessment?.verdict || textResult?.verdict;
  const displayConfidence = textAssessment?.confidence ?? textResult?.confidence;
  const displaySummary = textAssessment?.summary || textResult?.summary;
  const displayLimitations = textAssessment?.limitations || textResult?.limitations || [];
  const displayEvidence = textResult?.evidence || textResult?.sources || [];
  const claimType = textResult?.claim_details?.claim_type;

  // Multimodal image result fields
  const multimodalSynthesis = imageResult?.joint_interpretation || imageResult?.joint_assessment;
  const imageAssessmentData = imageResult?.image_assessment || imageResult?.image_result;
  const associatedTextAssessment = imageResult?.text_assessment;
  const associatedClaimText = imageResult?.claim_details?.original || imageResult?.claim;

  return (
    <div className="flex flex-col w-full max-w-4xl mx-auto px-4 sm:px-6 py-8 md:py-12 animate-in fade-in duration-500">
      
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-text-primary flex items-center gap-3">
          <ShieldCheck className="h-8 w-8 text-accent-blue" />
          DTI Verification Engine
        </h1>
        <p className="text-text-secondary mt-2 text-sm md:text-base">
          Cross-reference news headlines against evidence networks or inspect images for manipulation and compression anomalies.
        </p>
      </div>

      {/* Mode Selection Tabs */}
      <div className="mb-8 relative z-20 flex gap-2 border-b border-border-default">
        <button
          onClick={() => {
            setActiveTab('text');
            resetText();
            resetImage();
          }}
          className={`px-4 py-2.5 font-semibold text-sm border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'text'
              ? 'border-accent-blue text-accent-blue bg-accent-blue/5 rounded-t-lg'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`}
        >
          <Layers className="h-4 w-4" />
          Text Claim Verification
        </button>
        <button
          onClick={() => {
            setActiveTab('image');
            resetText();
            resetImage();
          }}
          className={`px-4 py-2.5 font-semibold text-sm border-b-2 transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'image'
              ? 'border-accent-blue text-accent-blue bg-accent-blue/5 rounded-t-lg'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`}
        >
          <Cpu className="h-4 w-4" />
          Image Forensics & Multimodal
        </button>
      </div>

      {/* Input Form Section */}
      <div className="mb-8 relative z-20">
        {activeTab === 'text' && (
          <ClaimInput 
            initialClaim={initialClaim} 
            onSubmit={handleTextVerifySubmit} 
            isLoading={isTextLoading} 
          />
        )}
        {activeTab === 'image' && (
          <ImageUpload 
            onImageSelected={handleImageVerifySubmit}
            isLoading={isImageLoading}
          />
        )}
      </div>

      {/* Dynamic Results Display Area */}
      <div className="flex flex-col gap-6" ref={resultRef}>
        
        {/* Empty States */}
        {activeTab === 'text' && !isTextLoading && !isTextError && !textResult && (
          <div className="text-center py-20 px-4 border border-border-dim border-dashed rounded-xl bg-background-secondary/30 transition-all">
            <p className="text-text-muted text-sm">Enter a news headline above to inspect supporting and refuting evidence.</p>
          </div>
        )}

        {activeTab === 'image' && !isImageLoading && !isImageError && !imageResult && (
          <div className="text-center py-20 px-4 border border-border-dim border-dashed rounded-xl bg-background-secondary/30 transition-all">
            <p className="text-text-muted text-sm">Upload an image above to run forensic residual and tampering analysis.</p>
          </div>
        )}

        {/* Loading Indicator */}
        {(isTextLoading || isImageLoading) && <LoadingState />}

        {/* Error States */}
        {isTextError && <ErrorState error={textError} onRetry={handleRetry} />}
        {isImageError && <ErrorState error={imageError} onRetry={() => resetImage()} />}

        {/* Text Verification Result Dashboard */}
        {isTextSuccess && textResult && !isTextLoading && !isTextError && (
          <div className="flex flex-col gap-6 w-full">
            <VerdictCard 
              claim={displayClaim}
              verdict={displayVerdict}
              confidence={displayConfidence}
              summary={displaySummary}
              conflictingSources={textResult.conflicting_sources}
              claimType={claimType}
            />

            {textResult.confidence_breakdown && (
              <ConfidenceBreakdownPanel breakdown={textResult.confidence_breakdown} />
            )}

            {textResult.agreement_signal && (
              <AgreementSignalPanel 
                signal={textResult.agreement_signal} 
                conflicting={textResult.conflicting_sources} 
              />
            )}

            {textResult.explanation && (
              <ExplanationBlock explanation={textResult.explanation} />
            )}

            {displayEvidence && displayEvidence.length > 0 && (
              <div className="mt-2">
                <EvidenceList 
                  evidence={textResult.evidence} 
                  sources={textResult.sources} 
                  limitations={displayLimitations}
                />
              </div>
            )}
          </div>
        )}

        {/* Image & Multimodal Verification Result Dashboard */}
        {isSuccess(isImageSuccess, imageResult, isImageLoading, isImageError) && (
          <div className="flex flex-col gap-6 w-full">
            {/* Multimodal Joint Synthesis Card */}
            {multimodalSynthesis && (
              <div className="p-5 rounded-xl bg-accent-blue/10 border border-accent-blue/30 text-text-primary flex flex-col gap-2 shadow-sm">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-accent-blue" />
                  <span className="text-xs font-bold uppercase tracking-wider text-accent-blue">
                    Multimodal Joint Synthesis
                  </span>
                </div>
                <p className="text-sm font-medium leading-relaxed">
                  {multimodalSynthesis}
                </p>
              </div>
            )}

            {/* Forensic Assessment Card */}
            {imageAssessmentData && (
              <ImageVerificationResult result={imageAssessmentData} />
            )}

            {/* If an associated text claim was submitted with the photo */}
            {associatedClaimText && (
              <div className="flex flex-col gap-4 mt-2">
                <h3 className="text-sm font-bold text-text-secondary uppercase tracking-wider">
                  Associated Claim Analysis
                </h3>

                {associatedTextAssessment?.status === 'unavailable' ? (
                  <div className="p-4 bg-background-card border border-border-default rounded-xl flex items-center gap-3 text-xs text-text-muted">
                    <AlertCircle className="h-4 w-4 text-amber-400 flex-shrink-0" />
                    <span>External knowledge search for the associated caption timed out or was temporarily unavailable.</span>
                  </div>
                ) : (
                  <>
                    <VerdictCard 
                      claim={associatedClaimText}
                      verdict={associatedTextAssessment?.verdict || imageResult.verdict}
                      confidence={associatedTextAssessment?.confidence ?? imageResult.confidence}
                      summary={associatedTextAssessment?.summary || imageResult.summary}
                      claimType={imageResult?.claim_details?.claim_type}
                    />

                    {imageResult.evidence && imageResult.evidence.length > 0 && (
                      <EvidenceList 
                        evidence={imageResult.evidence} 
                        limitations={associatedTextAssessment?.limitations || []}
                      />
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
};

// Helper for image success validation
function isSuccess(isSuccessFlag, result, isLoading, isError) {
  return isSuccessFlag && result && !isLoading && !isError;
}
