import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { claimsApi } from '../services/api'
import Card from '../components/Card'
import Input from '../components/Input'
import Button from '../components/Button'

export default function NewClaimPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // In a real app, this would come from authentication
  const userId = 'demo-user'

  const [formData, setFormData] = useState({
    claim_type: '',
    description: '',
    claim_amount: '',
  })

  const claimTypes = [
    { value: 'health', label: 'Assurance sante' },
    { value: 'auto', label: 'Assurance auto' },
    { value: 'home', label: 'Assurance habitation' },
    { value: 'life', label: 'Assurance vie' },
    { value: 'travel', label: 'Assurance voyage' },
    { value: 'other', label: 'Autre' },
  ]

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)

    if (!formData.claim_type || !formData.description || !formData.claim_amount) {
      setError('Veuillez remplir tous les champs')
      return
    }

    try {
      setLoading(true)
      const claim = await claimsApi.create({
        user_id: userId,
        claim_type: formData.claim_type,
        description: formData.description,
        claim_amount: parseFloat(formData.claim_amount),
      })

      // Navigate to claim detail page
      navigate(`/claims/${claim.id}`)
    } catch (err) {
      setError('Impossible de creer le sinistre. Veuillez reessayer.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Declarer un nouveau sinistre</h1>
        <p className="text-gray-600 mt-1">
          Fournissez les details de votre sinistre pour commencer
        </p>
      </div>

      <Card>
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Claim Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Type de sinistre
            </label>
            <select
              value={formData.claim_type}
              onChange={(e) =>
                setFormData({ ...formData, claim_type: e.target.value })
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              required
            >
              <option value="">Selectionnez un type de sinistre</option>
              {claimTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              placeholder="Decrivez ce qui s'est passe et ce que vous demandez..."
              required
            />
          </div>

          {/* Claim Amount */}
          <Input
            label="Montant du sinistre ($)"
            type="number"
            step="0.01"
            min="0"
            value={formData.claim_amount}
            onChange={(e) =>
              setFormData({ ...formData, claim_amount: e.target.value })
            }
            placeholder="0,00"
            required
          />

          {/* Error Message */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Info Box */}
          <div className="p-4 bg-blue-50 border border-blue-200 rounded-md">
            <p className="text-sm text-blue-800">
              Apres l'envoi, vous pourrez importer des documents justificatifs pour votre sinistre.
              Notre IA les verifiera automatiquement.
            </p>
          </div>

          {/* Submit Button */}
          <div className="flex gap-4">
            <Button type="submit" loading={loading} className="flex-1">
              Soumettre le sinistre
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/claims')}
              disabled={loading}
            >
              Annuler
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
