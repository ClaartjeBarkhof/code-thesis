import torch
from modules.decoder_roberta import VAE_Decoder_RobertaForCausalLM
import copy
from transformers import top_k_top_p_filtering
import torch.nn as nn
from utils_evaluation import tokenizer_batch_decode

class DecoderNewsVAE(torch.nn.Module):
    def __init__(self,
                 gradient_checkpointing=False,
                 add_latent_via_memory=True,
                 add_latent_via_embeddings=True,
                 latent_size=768):
        """
        Decoder of VAE based on a RobertaForCausalLM initialised with roberta-base checkpoint.
        """
        super(DecoderNewsVAE, self).__init__()

        self.model = VAE_Decoder_RobertaForCausalLM.from_pretrained("roberta-base",
                                                                    gradient_checkpointing=gradient_checkpointing)

        self.latent_size = latent_size
        self.n_layers = self.model.config.num_hidden_layers
        self.hidden_size = self.model.config.hidden_size
        self.initializer_range = self.model.config.initializer_range

        self.latent_to_decoder = LatentToDecoderNewsVAE(add_latent_via_memory=add_latent_via_memory,
                                                        add_latent_via_embeddings=add_latent_via_embeddings,
                                                        latent_size=self.latent_size,
                                                        hidden_size=self.hidden_size,
                                                        n_layers=self.n_layers,
                                                        initializer_range=self.initializer_range)

    def forward(self, latent_z, input_ids, attention_mask,
                labels=None,
                return_attention_probs=False,
                return_attention_to_latent=False,
                return_hidden_states=False,
                return_exact_match=False,
                return_predictions=False,
                return_probabilities=False,
                return_last_hidden_state=False,
                return_logits=False,
                return_cross_entropy=True,
                reduce_seq_dim_exact_match="mean",
                reduce_batch_dim_exact_match="mean",
                reduce_seq_dim_ce="sum",
                reduce_batch_dim_ce="mean",
                nucleus_sampling=False,
                top_k=0,
                top_p=0.9):
        """
        Make a (teacher-forced) forward pass through the decoder.

        Args:
            latent_z: Tensor [batch x latent_size]:
                Latent code in batch.
            input_ids: Tensor [batch x seq_len]
                Token input ids of the output so far or teacher-forced the whole seq.
            attention_mask: Tensor [batch x seq_len]
                Mask marking the padded tokens (0)
            labels: Tensor [batch x seq_len]

            return_attention_probs: bool
            return_attention_to_latent: bool

            return_hidden_states: bool
            return_last_hidden_state: bool

            return_predictions: bool
            return_probabilities: bool
            return_logits: bool

            return_cross_entropy: bool
            return_exact_match: bool
            reduce_seq_dim_ce: str
                How to reduce the sequence dimension for Cross Entropy: 'mean', 'sum', 'none'
            reduce_seq_dim_exact_match:
                How to reduce the sequence dimension for exact match: 'mean', 'sum', 'none'
            reduce_batch_dim_exact_match:
                How to reduce the batch dimension for exact match: 'mean', 'sum', 'none'
            reduce_batch_dim_ce:
                How to reduce the batch dimension for Cross Entropy: 'mean', 'sum', 'none'
            -> if the last two are mean, it returns exact match accuracy

            nucleus_sampling: bool
            top_k: int
            top_p: float

        Returns:
            decoder_outs: Dict[str, Union[Tensor, float]]
                Everything the decoder returns (predictions, reconstruction loss, etc.)
        """

        latent_to_decoder_output = self.latent_to_decoder(latent_z)

        # Forward the decoder
        decoder_outs = self.model(latent_to_decoder_output=latent_to_decoder_output,
                                  input_ids=input_ids,
                                  attention_mask=attention_mask,
                                  labels=labels,
                                  return_attention_probs=return_attention_probs,
                                  return_attention_to_latent=return_attention_to_latent,
                                  return_hidden_states=return_hidden_states,
                                  return_exact_match=return_exact_match,
                                  return_predictions=return_predictions,
                                  return_probabilities=return_probabilities,
                                  return_last_hidden_state=return_last_hidden_state,
                                  return_logits=return_logits,
                                  return_cross_entropy=return_cross_entropy,
                                  reduce_seq_dim_ce=reduce_seq_dim_ce,
                                  reduce_seq_dim_exact_match=reduce_seq_dim_exact_match,
                                  reduce_batch_dim_exact_match=reduce_batch_dim_exact_match,
                                  reduce_batch_dim_ce=reduce_batch_dim_ce,
                                  nucleus_sampling=nucleus_sampling,
                                  top_k=top_k,
                                  top_p=top_p)

        return decoder_outs

    # # TODO: check whether this works. The performance of this run was very poort
    # def reset_to_base_checkpoint(self, gradient_checkpointing=False,
    #                              do_tie_weights=False):
    #     """
    #     This function resets the decoder (re-initialise with base checkpoint).
    #
    #     Args:
    #         gradient_checkpointing: bool
    #             Whether or not to use gradient checkpointing, default: False
    #         do_tie_weights: bool
    #             Whether or not the weights between encoder and decoder are shared (for warning), default: False
    #
    #     """
    #
    #     print("Checking if shared_weights == False, yields {}".format(do_tie_weights == False))
    #     assert do_tie_weights is False, "Not resetting the decoder if the weights are shared. Aborting!"
    #
    #     print(f"Resetting the decoder to roberta-base checkpoint.")
    #     self.model = VAE_Decoder_RobertaForCausalLM.from_pretrained("roberta-base",
    #                                                                 gradient_checkpointing=gradient_checkpointing)

    # # TODO: NOT TESTED YET
    # def log_p_x_z(self, input_ids, attention_mask, latent_z, args):
    #     """
    #     This function evaluates the likelihood (negative cross-entropy) of outputs given some latents z.
    #     """
    #
    #     assert len(latent_z.shape) == 3, "Latent z must be of shape [batch, n_samples, latent_size]"
    #
    #     batch_size, seq_len = input_ids.shape
    #     n_samples = latent_z.shape[1]
    #
    #     losses = []
    #
    #     # Loop over batch dimension, sample dimension is interpreted as batch dimension
    #     for i in range(batch_size):
    #         z = latent_z[i, :, :].squeeze(0)
    #         x = input_ids[i, :].expand(n_samples, seq_len)
    #         a = attention_mask[i, :].expand(n_samples, seq_len)
    #
    #         # Forward the decoder
    #         decoder_outs = self.model(input_ids=x, attention_mask=a,
    #                                   latent_z=z, labels=copy.copy(x),
    #                                   add_latent_via_embeddings=args.add_latent_via_embeddings,
    #                                   add_latent_via_memory=args.add_latent_via_memory,
    #                                   return_cross_entropy=True,
    #                                   reduce_loss=False,
    #                                   return_predictions=False,
    #                                   return_exact_match_acc=False)
    #
    #         # Reconstruction loss = cross entropy = negative log likelihood
    #         recon_loss = decoder_outs["cross_entropy"]
    #         losses.append(recon_loss)
    #
    #     # Stack so the dimensions are batch_size x n_samples
    #     losses = torch.stack(losses)
    #
    #     # Reconstruction loss = cross entropy = negative log likelihood
    #     # so likelihood is the negative of that
    #     return - losses

    def autoregressive_decode(self, latent_z, max_seq_len=32,

                              labels=None,

                              return_exact_match=False,
                              return_cross_entropy=False,

                              reduce_seq_dim_ce="sum",
                              reduce_batch_dim_ce="mean",
                              reduce_seq_dim_exact_match="mean",
                              reduce_batch_dim_exact_match="mean",

                              return_attention_probs=False,
                              return_attention_to_latent=False,

                              return_hidden_states=False,
                              return_last_hidden_state=False,

                              return_predictions=True,

                              return_probabilities=False,
                              return_logits=False,

                              nucleus_sampling=False, top_k=0, top_p=0.0,
                              device_name="cuda:0"):
        """
        This function performs auto-regressive decoding (no grads), given samples from the latent space.

        Args:
            latent_z: Dict[str, Tensor]
                Latents transformed into correct forms (embeddings / memory) for the decoder.
            tokenizer:
            max_seq_len: int:
                How many sequential forward passes to perform:
                maximum sequence length for the whole batch.
            nucleus_sampling: bool
                Whether or not to perform top_k_top_p_filtering (nucleus sampling)
                top_k_top_p_filtering: Filter a distribution of logits using top-k and/or nucleus (top-p) filtering
            top_k: int
            top_p: float
            device_name: str:
                Which device to use for decoding (default: 'cuda:0')

        Returns:
            generated_so_far: Tensor [batch, max_seq_len]
                Batch of decoded / generated token ids
        """
        assert (return_exact_match or return_cross_entropy) is (
                labels is not None), "provide labels if return_exact_match_acc or return_cross_entropy is set to True"

        latent_to_decoder = self.latent_to_decoder(latent_z)
        batch_size = latent_z.shape[0]

        # Add <s> and </s>
        eos_token_id, bos_token_id = 2, 0

        generated_so_far = torch.tensor([[bos_token_id, eos_token_id] for _ in range(batch_size)])
        generated_so_far = generated_so_far.to(device_name)

        attention_to_latent, attention_probs = [], []
        hidden_states, last_hidden_state = [], []
        logits, probabilities = [], []
        exact_match, cross_entropy = [], []

        # Sequence length includes start and end token
        for i in range(max_seq_len - 1):
            if labels is not None:
                labels_so_far = labels[:, :i+2]
            else:
                labels_so_far = None

            decoder_outs = self.model(input_ids=generated_so_far, attention_mask=None,
                                      latent_to_decoder_output=latent_to_decoder, labels=labels_so_far,

                                      return_cross_entropy=return_cross_entropy,
                                      return_exact_match=return_exact_match,

                                      reduce_seq_dim_ce="none",
                                      reduce_batch_dim_ce="none",
                                      reduce_seq_dim_exact_match="none",
                                      reduce_batch_dim_exact_match="none",

                                      return_predictions=True,  # needed for input at every time step
                                      return_probabilities=return_probabilities,
                                      return_attention_to_latent=return_attention_to_latent,
                                      return_attention_probs=return_attention_probs,
                                      return_hidden_states=return_hidden_states,
                                      return_last_hidden_state=return_last_hidden_state,
                                      return_logits=return_logits,
                                      nucleus_sampling=nucleus_sampling,
                                      top_k=top_k,
                                      top_p=top_p)

            # Get the predictions of this time step
            new_preds = decoder_outs['predictions'][:, -1]

            if return_exact_match:
                exact_match.append(decoder_outs["exact_match"][:, -1])

            if return_cross_entropy:
                cross_entropy.append(decoder_outs["cross_entropy"][:, -1])

            if return_probabilities:
                probabilities.append(decoder_outs["probabilities"][:, -1, :].cpu())

            if return_logits:
                logits.append(decoder_outs["logits"][:, -1, :].cpu())

            if return_attention_probs:
                # batch, n_heads, n_layers, seq_len_query, seq_len_val
                # we only want the query dimension of the current prediction (-1 would be </s> prediction)
                attention_probs.append(decoder_outs["attention_probs"][:, :, :, -2, :])

            if return_attention_to_latent:
                # Get not the last token (which is predicting from </s> to nonsense), but the second to last
                attention_to_latent.append(decoder_outs["attention_to_latent"][:, :, :, -2].cpu())

            if return_hidden_states:
                hidden_states.append(decoder_outs["hidden_states"][:, :, -2, :].cpu())

            if return_last_hidden_state:
                last_hidden_state.append(decoder_outs["last_hidden_state"][:, -2, :].cpu())

            # Concat into <s> <predictions> </s> format for next round
            generated_so_far = torch.cat(
                (generated_so_far[:, :-1], new_preds.unsqueeze(1), generated_so_far[:, -1].unsqueeze(1)), dim=1)

        outputs = {}

        if return_logits:
            outputs["logits"] = torch.stack(logits, dim=1)

        if return_probabilities:
            outputs["probabilities"] = torch.stack(probabilities, dim=1)

        # what to do with attention_probs?
        if return_attention_probs:
            print("an ugly list of all (masked) attentionprobs coming back to you")
            outputs["attention_probs"] = attention_probs

        if return_attention_to_latent:
            outputs["attention_to_latent"] = torch.stack(attention_to_latent, dim=-1)

        predictions = generated_so_far[:, 1:-1]
        if return_predictions:
            # the </s> is not predicted, neither is the added </s>
            outputs["predictions"] = predictions

        if return_hidden_states:
            outputs["hidden_states"] = torch.stack(hidden_states, dim=2)

        if return_last_hidden_state:
            outputs["last_hidden_state"] = torch.stack(last_hidden_state, dim=1)

        if return_exact_match:
            outputs["exact_match"] = torch.stack(exact_match, dim=-1)
            outputs["exact_match"] = self.model.reduce_correct(outputs["exact_match"], reduce_seq_dim_exact_match, -1)  # seq dim
            outputs["exact_match"] = self.model.reduce_correct(outputs["exact_match"], reduce_batch_dim_exact_match, 0)  # batch dim

        if return_cross_entropy:
            outputs["cross_entropy"] = torch.stack(cross_entropy, dim=-1)
            outputs["cross_entropy"] = self.model.reduce_correct(outputs["cross_entropy"], reduce_seq_dim_ce, -1)  # seq dim
            outputs["cross_entropy"] = self.model.reduce_correct(outputs["cross_entropy"], reduce_batch_dim_ce, 0)  # batch dim <- always mean

        return outputs



class LatentToDecoderNewsVAE(nn.Module):
    def __init__(self, add_latent_via_memory=True,
                 add_latent_via_embeddings=True,
                 latent_size=768, hidden_size=768, n_layers=12,
                 initializer_range=0.02):
        """
        A module to connect the latents to a format that can be used by the DecoderNewsVAE.
        """

        super(LatentToDecoderNewsVAE, self).__init__()

        self.add_latent_via_memory = add_latent_via_memory
        self.add_latent_via_embeddings = add_latent_via_embeddings

        self.hidden_size = hidden_size

        # Latent via memory layer
        if self.add_latent_via_memory:
            self.latent_to_memory_projection = nn.Linear(latent_size, hidden_size * n_layers)
            self.latent_to_memory_projection.weight.data.normal_(mean=0.0, std=initializer_range)

        # Latent via embedding layer
        if self.add_latent_via_embeddings:
            self.latent_to_embedding_projection = nn.Linear(latent_size, hidden_size)
            self.latent_to_embedding_projection.weight.data.normal_(mean=0.0, std=initializer_range)

    def forward(self, latent_z):
        """
        Handles the connection between encoder and decoder by transforming
        the latent in such a way the decoder can use it.

        Args:
            latent_z: Tensor [batch, latent_size]
                The latents sampled from the encoded input posterior.
        Returns:
            output: Dict[str, Tensor]
                Depending on whether or not to add via memory and/or embeddings
                it returns a dict containing the right information to be used by decoder.
        """

        output = {"latent_to_memory": None,
                  "latent_to_embeddings": None}

        if self.add_latent_via_memory:
            latent_to_memory = self.latent_to_memory_projection(latent_z)
            # Makes tuple of equally sized tensors of (batch x 1 x hidden_size)
            latent_to_memory = torch.split(latent_to_memory.unsqueeze(1), self.hidden_size, dim=2)
            output["latent_to_memory"] = latent_to_memory

        if self.add_latent_via_embeddings:
            latent_to_embeddings = self.latent_to_embedding_projection(latent_z)
            output["latent_to_embeddings"] = latent_to_embeddings

        return output
