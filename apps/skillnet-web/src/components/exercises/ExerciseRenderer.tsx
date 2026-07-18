import { TestExercise } from './TestExercise'
import { TrueFalseExercise } from './TrueFalseExercise'
import { FillBlankExercise } from './FillBlankExercise'
import { OrderStepsExercise } from './OrderStepsExercise'
import { PracticalCaseExercise } from './PracticalCaseExercise'
import { DialogueExercise } from './DialogueExercise'
import type { Exercise } from '../../types'

// Dispatches an exercise to its type-specific renderer. Each renderer wires
// itself to useSubmitAttempt and shows the graded result.
export function ExerciseRenderer({ exercise }: { exercise: Exercise }) {
  switch (exercise.type) {
    case 'test':
      return <TestExercise exercise={exercise} />
    case 'true_false':
      return <TrueFalseExercise exercise={exercise} />
    case 'fill_blank':
      return <FillBlankExercise exercise={exercise} />
    case 'order_steps':
      return <OrderStepsExercise exercise={exercise} />
    case 'practical_case':
      return <PracticalCaseExercise exercise={exercise} />
    case 'dialogue':
      return <DialogueExercise exercise={exercise} />
    default:
      return null
  }
}
