import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Upload, FileText, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { claimsApi, documentsApi } from '../services/api'
import type { Claim, Document } from '../types'
import { DocumentType } from '../types'
import Card from '../components/Card'
import Button from '../components/Button'
import Badge from '../components/Badge'

export default function ClaimDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [claim, setClaim] = useState<Claim | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedDocType, setSelectedDocType] = useState<string>('')

  useEffect(() => {
    if (id) {
      loadClaim()
      loadDocuments()
    }
  }, [id])

  const loadClaim = async () => {
    try {
      setLoading(true)
      const data = await claimsApi.getById(parseInt(id!))
      setClaim(data)
    } catch (err) {
      setError('Failed to load claim')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const loadDocuments = async () => {
    try {
      const data = await documentsApi.getByClaimId(parseInt(id!))
      setDocuments(data)
    } catch (err) {
      console.error('Failed to load documents:', err)
    }
  }

  const handleFileUpload = async () => {
    if (!selectedFile || !selectedDocType) {
      setError('Veuillez selectionner un fichier et un type de document')
      return
    }

    try {
      setUploading(true)
      setError(null)
      await documentsApi.upload(selectedFile, parseInt(id!), selectedDocType)

      // Reset form
      setSelectedFile(null)
      setSelectedDocType('')

      // Reload documents
      await loadDocuments()
      await loadClaim()
    } catch (err) {
      setError('Impossible d\'importer le document')
      console.error(err)
    } finally {
      setUploading(false)
    }
  }

  const claimTypeLabels: Record<string, string> = {
    health: 'Sante',
    auto: 'Auto',
    home: 'Habitation',
    life: 'Vie',
    travel: 'Voyage',
    other: 'Autre',
  }

  const formatClaimType = (claimType: string) =>
    claimTypeLabels[claimType] ?? claimType.replace('_', ' ')

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('fr-FR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'USD',
    }).format(amount)

  const getVerificationIcon = (doc: Document) => {
    switch (doc.verification_status) {
      case 'verified':
        return <CheckCircle className="w-5 h-5 text-green-600" />
      case 'rejected':
        return <XCircle className="w-5 h-5 text-red-600" />
      case 'partially_compliant':
        return <AlertCircle className="w-5 h-5 text-orange-600" />
      default:
        return <AlertCircle className="w-5 h-5 text-gray-400" />
    }
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Card>
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
              <p className="mt-4 text-gray-600">Chargement du sinistre...</p>
            </div>
          </Card>
        </div>
      )
    }

  if (!claim) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Card className="border-red-200 bg-red-50">
          <p className="text-red-600">Sinistre introuvable</p>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Claim Header */}
      <Card className="mb-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">
              {claim.claim_number}
            </h1>
            <Badge status={claim.status} />
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-500">Declare le</p>
            <p className="text-gray-900 font-medium">{formatDate(claim.created_at)}</p>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-6 mt-6">
          <div>
            <p className="text-sm text-gray-500">Type de sinistre</p>
            <p className="text-gray-900 font-medium capitalize">
              {formatClaimType(claim.claim_type)}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Montant du sinistre</p>
            <p className="text-gray-900 font-medium">
              {formatCurrency(claim.claim_amount)}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Derniere mise a jour</p>
            <p className="text-gray-900 font-medium">
              {formatDate(claim.updated_at)}
            </p>
          </div>
        </div>

        <div className="mt-6">
          <p className="text-sm text-gray-500 mb-1">Description</p>
          <p className="text-gray-900">{claim.description}</p>
        </div>

        {claim.status_message && (
          <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-md">
            <p className="text-sm text-blue-800">{claim.status_message}</p>
          </div>
        )}
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Upload Documents */}
        <Card>
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Importer des documents
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Type de document
              </label>
              <select
                value={selectedDocType}
                onChange={(e) => setSelectedDocType(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">Selectionnez un type de document</option>
                <option value={DocumentType.IDENTITY}>Piece d'identite</option>
                <option value={DocumentType.MEDICAL_REPORT}>Rapport medical</option>
                <option value={DocumentType.INVOICE}>Facture/Recu</option>
                <option value={DocumentType.POLICE_REPORT}>Rapport de police</option>
                <option value={DocumentType.PROOF_OF_OWNERSHIP}>Preuve de propriete</option>
                <option value={DocumentType.PHOTOS}>Photos</option>
                <option value={DocumentType.OTHER}>Autre</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Selectionnez un fichier
              </label>
              <input
                type="file"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                accept="image/*,.pdf"
              />
            </div>

            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                <p className="text-sm text-red-600">{error}</p>
              </div>
            )}

            <Button
              onClick={handleFileUpload}
              loading={uploading}
              disabled={!selectedFile || !selectedDocType}
              className="w-full"
            >
              <Upload className="w-4 h-4 mr-2" />
              Importer et verifier le document
            </Button>

            <p className="text-xs text-gray-500">
              Formats acceptes : JPG, PNG, PDF. Notre IA verifiera automatiquement votre document.
            </p>
          </div>
        </Card>

        {/* Documents List */}
        <Card>
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Documents importes ({documents.length})
          </h2>

          {documents.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <FileText className="w-12 h-12 mx-auto mb-2 text-gray-400" />
              <p>Aucun document importe pour le moment</p>
            </div>
          ) : (
            <div className="space-y-3">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="border border-gray-200 rounded-lg p-4 hover:shadow-sm transition-shadow"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {getVerificationIcon(doc)}
                      <div>
                        <p className="font-medium text-gray-900 text-sm">
                          {doc.filename}
                        </p>
                        <p className="text-xs text-gray-500 capitalize">
                          {doc.document_type.replace('_', ' ')}
                        </p>
                      </div>
                    </div>
                  </div>

                  {doc.confidence_score !== null && (
                    <div className="mb-2">
                      <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                        <span>Confiance</span>
                        <span>{doc.confidence_score}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${
                            doc.confidence_score >= 80
                              ? 'bg-green-500'
                              : doc.confidence_score >= 60
                              ? 'bg-orange-500'
                              : 'bg-red-500'
                          }`}
                          style={{ width: `${doc.confidence_score}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {doc.compliance_issues && (
                    <div className="mt-2 p-2 bg-orange-50 border border-orange-200 rounded text-xs text-orange-800">
                      {doc.compliance_issues}
                    </div>
                  )}

                  <p className="text-xs text-gray-500 mt-2">
                    Importe le {formatDate(doc.uploaded_at)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
