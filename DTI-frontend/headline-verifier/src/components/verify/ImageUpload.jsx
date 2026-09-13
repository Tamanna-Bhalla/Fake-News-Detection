import { useState, useRef } from 'react';
import { Upload, X, Image as ImageIcon, FileText, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Button } from '../ui/Button';

export const ImageUpload = ({ onImageSelected, isLoading }) => {
  const [previewUrl, setPreviewUrl] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileDetails, setFileDetails] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [claim, setClaim] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const validExtensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff'];
  const maxSizeBytes = 10 * 1024 * 1024; // 10MB

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const handleFile = (file) => {
    if (!file) return;
    setErrorMessage(null);

    // Validate extension
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!validExtensions.includes(ext)) {
      setErrorMessage(`Unsupported format (${ext}). Please select JPEG, PNG, WebP, BMP, TIFF, or GIF.`);
      return;
    }

    // Validate size
    if (file.size > maxSizeBytes) {
      setErrorMessage(`File is too large (${formatFileSize(file.size)}). Maximum upload size is 10 MB.`);
      return;
    }

    if (file.size === 0) {
      setErrorMessage('The selected file is empty (0 bytes).');
      return;
    }

    setSelectedFile(file);

    // Read preview and dimensions
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target.result;
      setPreviewUrl(dataUrl);

      const img = new Image();
      img.onload = () => {
        setFileDetails({
          name: file.name,
          size: formatFileSize(file.size),
          width: img.naturalWidth,
          height: img.naturalHeight,
          format: ext.replace('.', '').toUpperCase(),
        });

        if (img.naturalWidth < 32 || img.naturalHeight < 32) {
          setErrorMessage(`Resolution too low (${img.naturalWidth}x${img.naturalHeight}px). Minimum is 32x32px for forensic analysis.`);
        }
      };
      img.src = dataUrl;
    };
    reader.readAsDataURL(file);
  };

  const handleInputChange = (e) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleSubmit = () => {
    if (selectedFile && !isLoading && !errorMessage) {
      onImageSelected(selectedFile, claim.trim() || null);
    }
  };

  const handleClear = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setFileDetails(null);
    setErrorMessage(null);
    setClaim('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="w-full flex flex-col gap-4">
      {/* Upload Zone & Preview */}
      <div className="flex flex-col sm:flex-row gap-4">
        {/* Drop Zone */}
        <div
          className={`flex-1 relative flex flex-col items-center justify-center border-2 border-dashed rounded-xl transition-all duration-200 p-6 cursor-pointer select-none ${
            dragActive
              ? 'border-accent-blue bg-accent-blue/15 scale-[0.99]'
              : selectedFile
              ? 'border-border-default bg-background-secondary/30 hover:border-accent-blue/40'
              : 'border-border-default bg-background-secondary/50 hover:border-accent-blue/50'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !selectedFile && fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="Upload image for forensic analysis"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff,image/gif"
            onChange={handleInputChange}
            className="hidden"
            disabled={isLoading}
          />

          {!previewUrl ? (
            <div className="flex flex-col items-center gap-2 text-center">
              <div className="h-12 w-12 rounded-full bg-accent-blue/10 flex items-center justify-center text-accent-blue mb-1">
                <Upload className="h-6 w-6" />
              </div>
              <div>
                <p className="text-text-primary font-semibold">Upload Image for Forensics</p>
                <p className="text-text-secondary text-xs mt-0.5">
                  Drag and drop here, or click to browse
                </p>
              </div>
              <p className="text-text-muted text-[11px] mt-1">
                JPEG, PNG, WebP, BMP, TIFF, GIF (Up to 10 MB)
              </p>
            </div>
          ) : (
            <div className="text-center">
              <ImageIcon className="h-8 w-8 text-accent-blue mx-auto mb-2" />
              <p className="text-text-primary font-medium text-sm line-clamp-1">{fileDetails?.name || 'Image selected'}</p>
              <p className="text-text-secondary text-xs mt-1">Click to replace photo</p>
            </div>
          )}
        </div>

        {/* Client-side Live Preview Card */}
        {previewUrl && fileDetails && (
          <div className="relative w-full sm:w-52 rounded-xl overflow-hidden border border-border-default bg-background-secondary flex flex-col flex-shrink-0 shadow-sm">
            <div className="relative h-32 w-full bg-black/40 overflow-hidden flex items-center justify-center">
              <img
                src={previewUrl}
                alt="Upload Preview"
                className="w-full h-full object-contain"
              />
              <button
                onClick={handleClear}
                disabled={isLoading}
                className="absolute top-2 right-2 p-1.5 bg-black/70 hover:bg-red-600/90 text-white rounded-lg transition-colors disabled:opacity-50"
                title="Remove image"
                aria-label="Remove image"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-3 text-[11px] text-text-muted flex flex-col gap-1 border-t border-border-dim bg-background-card">
              <div className="flex justify-between">
                <span>Format:</span>
                <strong className="text-text-primary">{fileDetails.format}</strong>
              </div>
              <div className="flex justify-between">
                <span>Resolution:</span>
                <strong className="text-text-primary">{fileDetails.width} &times; {fileDetails.height}px</strong>
              </div>
              <div className="flex justify-between">
                <span>File Size:</span>
                <strong className="text-text-primary">{fileDetails.size}</strong>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Validation Error Message */}
      {errorMessage && (
        <div className="p-3 bg-verdict-false/10 border border-verdict-false/30 rounded-xl flex items-start gap-2.5 text-xs text-verdict-false animate-in fade-in duration-200">
          <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Optional Associated Claim Input */}
      {selectedFile && !errorMessage && (
        <div className="flex flex-col gap-1.5 p-3.5 rounded-xl bg-background-secondary/40 border border-border-default/60">
          <label className="text-xs font-semibold text-text-secondary flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5 text-accent-blue" />
            Associated News Claim or Headline (Optional)
          </label>
          <input
            type="text"
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            placeholder="e.g. 'Photo shows wildfire approaching residential zone today'"
            disabled={isLoading}
            maxLength={500}
            className="w-full px-3 py-2 text-sm bg-background-card border border-border-default rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-blue transition-colors"
          />
          <p className="text-[11px] text-text-muted">
            Evaluating an associated claim enables joint multimodal synthesis comparing caption veracity with visual authenticity.
          </p>
        </div>
      )}

      {/* Submit Action */}
      {selectedFile && (
        <Button
          onClick={handleSubmit}
          disabled={!selectedFile || isLoading || !!errorMessage}
          isLoading={isLoading}
          className="w-full"
        >
          {isLoading
            ? 'Performing Forensic Residual & Tampering Analysis...'
            : claim.trim()
            ? 'Verify Image & Associated Claim'
            : 'Analyze Image Forensics'}
        </Button>
      )}
    </div>
  );
};
